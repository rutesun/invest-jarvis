"""Chart-only diagnostic state must never become an entry gate."""

from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.strategies.models import (
    BarFinality,
    ChartBar,
    ChartBundle,
    ChartSeries,
    CoverageManifest,
    EntryOpportunityStatus,
    EntrySourceAnchors,
    SignalEntryOpportunity,
    SignalFinality,
    StrategySignal,
    StructureStatus,
)
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


def _inputs(closes=(110, 99), *, code="TREND_BREAKOUT_ENTRY", provisional=False):
    days = tuple(date(2026, 9, 1) + timedelta(days=i) for i in range(len(closes)))
    bars = tuple(
        ChartBar(
            session_date=day,
            open=Decimal(str(close)),
            high=Decimal(str(close + 1)),
            low=Decimal(str(close - 1)),
            close=Decimal(str(close)),
            volume=Decimal("1000"),
            finality=(
                BarFinality.PROVISIONAL if provisional and day == days[-1] else BarFinality.FINAL
            ),
        )
        for day, close in zip(days, closes, strict=True)
    )
    bundle = ChartBundle(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=days[-1],
        instrument=ChartSeries(
            bars=bars,
            coverage=CoverageManifest(
                requested_start=days[0],
                actual_start=days[0],
                actual_end=days[-1],
                expected_sessions=days,
                complete=True,
            ),
        ),
        exchange_sessions=days,
    )
    evidence = Evidence(
        code="entry",
        message="entry",
        observed_value=110,
        reference_value=100,
        importance=Importance.MEDIUM,
        source="SWING_W150",
    )
    source = StrategySignal(
        signal_id="source",
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="production",
        parameter_fingerprint="production-fingerprint",
        code=code,
        occurred_on=days[0],
        finality=SignalFinality.FINAL,
        direction=None,
        signal_price=Decimal("110"),
        evidence=[evidence],
        data_status=DataStatus.COMPLETE,
    )
    anchors = EntrySourceAnchors(
        source_id=source.signal_id,
        source_date=source.occurred_on,
        source_type=code,
        signal_price=source.signal_price,
        atr_at_signal=Decimal("5"),
        breakout_level=Decimal("100"),
        origin_support=Decimal("100"),
        pullback_low=Decimal("95"),
        anchor_finality=source.finality,
        policy_version="production",
    )
    opportunity = SignalEntryOpportunity(
        evaluation_as_of=bundle.as_of,
        finality=SignalFinality(bars[-1].finality.value),
        status=EntryOpportunityStatus.ALLOW,
        entry_signal=source,
        invalidated_by=None,
        age_bars=len(bars) - 1,
        signal_price=source.signal_price,
        execution_reference_price=None,
        extension_pct=None,
        market_regime="RISK_ON",
        structure_status=StructureStatus.VALID,
        evidence=[evidence],
        policy_version="production",
        anchors=anchors,
    )
    return opportunity, bundle


def _evaluate(opportunity, bundle, **kwargs):
    from src.strategies.entry_shadow import evaluate_entry_shadow

    return evaluate_entry_shadow(opportunity, bundle, **kwargs)


def _codes(result):
    return {flag.code for flag in result.risk_flags}


def test_breakout_breach_reclaim_is_current_diagnostic_and_keeps_production_untouched():
    opportunity, bundle = _inputs((110, 99, 100))
    before = opportunity.model_dump(mode="json")
    breach = _evaluate(opportunity, bundle.prefix(date(2026, 9, 2)))
    assert breach.risk_level == "CAUTION"
    assert "BREAKOUT_LEVEL_BREACH" in _codes(breach)
    assert breach.breakout_states["B1"].status == "BREACHED"
    recovered = _evaluate(opportunity, bundle)
    assert recovered.risk_level == "NORMAL"
    assert _codes(recovered) == {"BREAKOUT_LEVEL_RECLAIMED"}
    assert recovered.breakout_states["B1"].status == "RECLAIMED"
    assert opportunity.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("closes", "early"),
    [
        ((110, 95), True),
        ((110, 110, 110, 110, 110, 95), True),
        ((110, 110, 110, 110, 110, 110, 95), False),
    ],
)
def test_three_atr_adverse_is_high_risk_and_early_failure_ends_after_five_bars(closes, early):
    result = _evaluate(*_inputs(closes))
    assert result.risk_level == "HIGH_RISK"
    assert "LARGE_ADVERSE_MOVE" in _codes(result)
    assert ("EARLY_FAILED_BREAKOUT_CANDIDATE" in _codes(result)) is early
    assert (result.breakout_states["B4"].status == "FAILURE_CANDIDATE") is early


def test_large_adverse_without_structure_breach_is_not_an_early_failed_breakout():
    opportunity, bundle = _inputs((110, 95))
    opportunity.anchors = opportunity.anchors.model_copy(update={"breakout_level": Decimal("90")})
    result = _evaluate(opportunity, bundle)
    assert result.risk_level == "HIGH_RISK"
    assert _codes(result) == {"LARGE_ADVERSE_MOVE"}


def test_early_failure_candidate_survives_window_until_structure_reclaim():
    opportunity, bundle = _inputs((110, 99, 99, 99, 99, 95, 99, 101))
    beyond_window = _evaluate(opportunity, bundle.prefix(date(2026, 9, 7)))
    assert beyond_window.breakout_states["B4"].status == "FAILURE_CANDIDATE"
    assert beyond_window.risk_level == "HIGH_RISK"
    assert "EARLY_FAILED_BREAKOUT_CANDIDATE" in _codes(beyond_window)
    assert "LARGE_ADVERSE_MOVE" not in _codes(beyond_window)
    assert beyond_window.breakout_states["B4"].candidate_on == date(2026, 9, 6)
    candidate = next(flag for flag in beyond_window.risk_flags if flag.code.startswith("EARLY_"))
    assert candidate.evidence[0].observed_value == 95
    recovered = _evaluate(opportunity, bundle)
    assert recovered.breakout_states["B4"].status == "RECLAIMED"
    assert recovered.breakout_states["B4"].candidate_on is None
    assert recovered.risk_level == "NORMAL"
    assert _codes(recovered) == {"BREAKOUT_LEVEL_RECLAIMED"}


def test_pullback_support_and_low_breach_reclaim_are_independent():
    opportunity, bundle = _inputs((110, 99, 94, 96, 100), code="PULLBACK_REVERSAL_ENTRY")
    support = _evaluate(opportunity, bundle.prefix(date(2026, 9, 2)))
    assert support.risk_level == "CAUTION"
    assert _codes(support) == {"ORIGIN_SUPPORT_BREACH"}
    low = _evaluate(opportunity, bundle.prefix(date(2026, 9, 3)))
    assert low.risk_level == "HIGH_RISK"
    assert "PULLBACK_LOW_BREACH" in _codes(low)
    assert low.pullback_states["P2"].status == "FAILURE_CANDIDATE"
    assert low.pullback_states["P3"].consecutive_low_closes == 1
    partial = _evaluate(opportunity, bundle.prefix(date(2026, 9, 4)))
    assert partial.risk_level == "CAUTION"
    assert _codes(partial) == {"ORIGIN_SUPPORT_BREACH", "PULLBACK_LOW_RECLAIMED"}
    assert partial.pullback_states["P3"].status == "BREACHED"
    assert partial.pullback_states["P3"].consecutive_low_closes == 0
    reclaimed = _evaluate(opportunity, bundle)
    assert reclaimed.risk_level == "NORMAL"
    assert reclaimed.pullback_states["P3"].status == "RECLAIMED"
    assert "ORIGIN_SUPPORT_RECLAIMED" in _codes(reclaimed)


def test_p3_requires_two_consecutive_low_closes_and_reclaims_at_maximum_anchor():
    opportunity, bundle = _inputs((110, 94, 94, 98), code="PULLBACK_REVERSAL_ENTRY")
    opportunity.anchors = opportunity.anchors.model_copy(update={"origin_support": Decimal("90")})
    first = _evaluate(opportunity, bundle.prefix(date(2026, 9, 2)))
    assert first.pullback_states["P2"].status == "CLEAR"
    assert first.pullback_states["P3"].status == "BREACHED"
    repeated = _evaluate(opportunity, bundle.prefix(date(2026, 9, 3)))
    assert repeated.pullback_states["P3"].status == "FAILURE_CANDIDATE"
    assert "SEVERE_PULLBACK_DETERIORATION" in _codes(repeated)
    reclaimed = _evaluate(opportunity, bundle)
    assert reclaimed.risk_level == "NORMAL"
    assert reclaimed.pullback_states["P3"].status == "RECLAIMED"


@pytest.mark.parametrize("code", ["DEEP_RECOVERY_ENTRY", "POST_OVERHEAT_RECOVERY_ENTRY"])
def test_unsupported_source_is_not_evaluated_without_normal_risk(code):
    result = _evaluate(*_inputs(code=code))
    assert result.data_status is DataStatus.NOT_EVALUATED
    assert result.reason == "UNSUPPORTED_SOURCE"
    assert result.risk_level is None


@pytest.mark.parametrize("missing", ["anchors", "atr_at_signal", "breakout_level"])
def test_missing_breakout_anchors_are_not_a_normal_assessment(missing):
    opportunity, bundle = _inputs()
    if missing == "anchors":
        opportunity.anchors = None
    else:
        opportunity.anchors = opportunity.anchors.model_copy(update={missing: None})
    result = _evaluate(opportunity, bundle)
    assert result.data_status is DataStatus.NOT_EVALUATED
    assert result.reason.startswith("MISSING_")
    assert result.risk_level is None
    assert result.risk_flags == []


def test_missing_pullback_low_does_not_silently_evaluate_p1_only():
    opportunity, bundle = _inputs(code="PULLBACK_REVERSAL_ENTRY")
    opportunity.anchors = opportunity.anchors.model_copy(update={"pullback_low": None})
    result = _evaluate(opportunity, bundle)
    assert result.data_status is DataStatus.NOT_EVALUATED
    assert result.risk_level is None


def test_provisional_reclaim_keeps_last_final_breach_visible():
    opportunity, bundle = _inputs((110, 99, 101), provisional=True)
    result = _evaluate(opportunity, bundle)
    assert result.finality is SignalFinality.PROVISIONAL
    state = result.breakout_states["B1"]
    assert state.status == "RECLAIMED"
    assert state.finality is SignalFinality.PROVISIONAL
    assert state.confirmed_status == "BREACHED"
    assert state.confirmed_as_of == date(2026, 9, 2)
    assert result.risk_flags[0].finality is SignalFinality.PROVISIONAL
    assert result.risk_flags[0].evidence


def test_provisional_anchor_cannot_produce_confirmed_shadow_state():
    opportunity, bundle = _inputs()
    opportunity.anchors = opportunity.anchors.model_copy(
        update={"anchor_finality": SignalFinality.PROVISIONAL}
    )
    result = _evaluate(opportunity, bundle)
    assert result.finality is SignalFinality.PROVISIONAL
    assert result.breakout_states["B1"].confirmed_status is None


def test_chart_prefix_determinism_and_no_future_outcome_reads():
    opportunity, full = _inputs((110, 99, 101, 90))
    prefix = full.prefix(date(2026, 9, 3))
    bounded = opportunity.model_copy(update={"evaluation_as_of": prefix.as_of})
    assert _evaluate(opportunity, prefix).model_dump(mode="json") == _evaluate(
        bounded, prefix
    ).model_dump(mode="json")


def test_final_production_terminal_is_unchanged_by_current_reclaim():
    opportunity, bundle = _inputs((110, 94, 101))
    opportunity = opportunity.model_copy(
        update={
            "status": EntryOpportunityStatus.EXPIRED,
            "terminal_on": date(2026, 9, 2),
            "terminal_finality": SignalFinality.FINAL,
        }
    )
    before = opportunity.model_dump(mode="json")
    assert _evaluate(opportunity, bundle).risk_level == "NORMAL"
    assert opportunity.model_dump(mode="json") == before


def test_research_parameters_are_frozen_and_change_shadow_identity_only():
    from src.strategies.entry_shadow import EntryShadowParameters

    opportunity, bundle = _inputs((110, 96))
    before = opportunity.model_dump(mode="json")
    default = EntryShadowParameters()
    alternate = EntryShadowParameters(adverse_atr_multiple=Decimal("2"))
    with pytest.raises(FrozenInstanceError):
        default.initial_bars = 6
    normal = _evaluate(opportunity, bundle, params=default)
    research = _evaluate(opportunity, bundle, params=alternate)
    assert normal.risk_level == "CAUTION"
    assert research.risk_level == "HIGH_RISK"
    assert normal.parameter_fingerprint != research.parameter_fingerprint
    assert normal.policy_version == "WATCH_RECLAIM_SHADOW_V1"
    assert opportunity.model_dump(mode="json") == before
