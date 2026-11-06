"""Risk dates describe current flag episodes without changing recorded decisions."""

from datetime import date
from decimal import Decimal

from src.strategies.entry_shadow import evaluate_entry_shadow
from src.strategies.models import BarFinality, ChartBundle, EntryRiskFlag, SignalFinality
from tests.strategies.test_entry_shadow import _inputs


def _flags(opportunity, bundle):
    return {flag.code: flag for flag in evaluate_entry_shadow(opportunity, bundle).risk_flags}


def test_breach_and_reclaim_keep_episode_dates_until_a_new_breach():
    opportunity, bundle = _inputs((110, 99, 98, 101, 102, 99))
    breach = _flags(opportunity, bundle.prefix(date(2026, 9, 3)))["BREAKOUT_LEVEL_BREACH"]
    assert breach.occurred_on == date(2026, 9, 2)
    assert breach.confirmed_on == date(2026, 9, 2)
    reclaimed = _flags(opportunity, bundle.prefix(date(2026, 9, 5)))["BREAKOUT_LEVEL_RECLAIMED"]
    assert reclaimed.occurred_on == date(2026, 9, 4)
    assert reclaimed.confirmed_on == date(2026, 9, 4)
    renewed = _flags(opportunity, bundle)["BREAKOUT_LEVEL_BREACH"]
    assert renewed.occurred_on == date(2026, 9, 6)
    assert renewed.confirmed_on == date(2026, 9, 6)


def test_provisional_breach_is_unconfirmed_then_final_bar_confirms_same_occurrence():
    opportunity, provisional = _inputs((110, 99), provisional=True)
    flag = _flags(opportunity, provisional)["BREAKOUT_LEVEL_BREACH"]
    assert flag.occurred_on == date(2026, 9, 2)
    assert flag.confirmed_on is None
    _, final = _inputs((110, 99, 98))
    flag = _flags(opportunity, final)["BREAKOUT_LEVEL_BREACH"]
    assert flag.occurred_on == date(2026, 9, 2)
    assert flag.confirmed_on == date(2026, 9, 2)
    opportunity.anchors = opportunity.anchors.model_copy(
        update={"anchor_finality": SignalFinality.PROVISIONAL}
    )
    flag = _flags(opportunity, final)["BREAKOUT_LEVEL_BREACH"]
    assert flag.finality is SignalFinality.PROVISIONAL
    assert flag.confirmed_on is None


def test_early_candidate_dates_start_at_deterioration_and_survive_the_window():
    opportunity, bundle = _inputs((110, 99, 99, 99, 99, 95, 99))
    flags = _flags(opportunity, bundle)
    assert flags["BREAKOUT_LEVEL_BREACH"].occurred_on == date(2026, 9, 2)
    candidate = flags["EARLY_FAILED_BREAKOUT_CANDIDATE"]
    assert candidate.occurred_on == date(2026, 9, 6)
    assert candidate.confirmed_on == date(2026, 9, 6)
    assert candidate.evidence[0].observed_value == 95


def test_historical_provisional_candidate_cannot_be_promoted_by_later_final_bars():
    opportunity, bundle = _inputs((110, 94, 99, 99))
    payload = bundle.model_dump(exclude={"bundle_hash"})
    payload["instrument"]["bars"][1]["finality"] = BarFinality.PROVISIONAL
    bundle = ChartBundle.model_validate(payload)
    candidate = _flags(opportunity, bundle)["EARLY_FAILED_BREAKOUT_CANDIDATE"]
    assert candidate.occurred_on == date(2026, 9, 2)
    assert candidate.finality is SignalFinality.PROVISIONAL
    assert candidate.confirmed_on is None


def test_current_provisional_breach_keeps_prior_final_confirmation_but_reclaim_does_not():
    opportunity, bundle = _inputs((110, 99, 98), provisional=True)
    flag = _flags(opportunity, bundle)["BREAKOUT_LEVEL_BREACH"]
    assert flag.finality is SignalFinality.PROVISIONAL
    assert flag.occurred_on == date(2026, 9, 2)
    assert flag.confirmed_on == date(2026, 9, 2)
    opportunity, bundle = _inputs((110, 99, 101), provisional=True)
    flag = _flags(opportunity, bundle)["BREAKOUT_LEVEL_RECLAIMED"]
    assert flag.occurred_on == date(2026, 9, 3)
    assert flag.confirmed_on is None


def test_pullback_low_and_origin_have_independent_breach_and_reclaim_dates():
    opportunity, bundle = _inputs((110, 99, 94, 96, 97, 100, 101), code="PULLBACK_REVERSAL_ENTRY")
    flags = _flags(opportunity, bundle.prefix(date(2026, 9, 3)))
    assert flags["ORIGIN_SUPPORT_BREACH"].occurred_on == date(2026, 9, 2)
    assert flags["PULLBACK_LOW_BREACH"].occurred_on == date(2026, 9, 3)
    assert flags["SEVERE_PULLBACK_DETERIORATION"].occurred_on == date(2026, 9, 3)
    flags = _flags(opportunity, bundle)
    assert flags["PULLBACK_LOW_RECLAIMED"].occurred_on == date(2026, 9, 4)
    assert flags["ORIGIN_SUPPORT_RECLAIMED"].occurred_on == date(2026, 9, 6)


def test_repeated_low_threshold_date_differs_from_first_low_breach():
    opportunity, bundle = _inputs((110, 94, 94, 94), code="PULLBACK_REVERSAL_ENTRY")
    opportunity.anchors = opportunity.anchors.model_copy(update={"origin_support": Decimal("90")})
    flags = _flags(opportunity, bundle)
    assert flags["PULLBACK_LOW_BREACH"].occurred_on == date(2026, 9, 2)
    assert flags["SEVERE_PULLBACK_DETERIORATION"].occurred_on == date(2026, 9, 3)
    assert flags["SEVERE_PULLBACK_DETERIORATION"].confirmed_on == date(2026, 9, 3)


def test_large_adverse_dates_restart_and_ignore_pre_source_and_future_bars():
    opportunity, bundle = _inputs((110, 94, 96, 94, 94))
    flags = _flags(opportunity, bundle)
    assert flags["LARGE_ADVERSE_MOVE"].occurred_on == date(2026, 9, 4)
    prefix_flags = _flags(opportunity, bundle.prefix(date(2026, 9, 3)))
    assert "LARGE_ADVERSE_MOVE" not in prefix_flags
    opportunity.entry_signal = opportunity.entry_signal.model_copy(
        update={"occurred_on": date(2026, 9, 3)}
    )
    opportunity.anchors = opportunity.anchors.model_copy(update={"source_date": date(2026, 9, 3)})
    flags = _flags(opportunity, bundle)
    assert flags["BREAKOUT_LEVEL_BREACH"].occurred_on == date(2026, 9, 4)
    assert flags["LARGE_ADVERSE_MOVE"].occurred_on == date(2026, 9, 4)


def test_risk_date_metadata_does_not_change_serialized_or_legacy_payload():
    opportunity, bundle = _inputs((110, 99))
    before = opportunity.model_dump(mode="json")
    result = evaluate_entry_shadow(opportunity, bundle)
    flag = result.risk_flags[0]
    assert flag.occurred_on == date(2026, 9, 2)
    assert set(flag.model_dump()) == {"code", "message", "finality", "evidence"}
    assert "occurred_on" not in result.model_dump(mode="json")["risk_flags"][0]
    assert "confirmed_on" not in result.model_dump(mode="json")["risk_flags"][0]
    legacy = EntryRiskFlag.model_validate(flag.model_dump())
    assert legacy.occurred_on is None
    assert legacy.confirmed_on is None
    assert opportunity.model_dump(mode="json") == before
