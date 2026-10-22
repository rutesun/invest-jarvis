from datetime import date
from decimal import Decimal

import pytest

from src.position.models import DirectiveKind
from src.position.policy import decide_directive
from src.strategies.models import (
    EntryIntent,
    EntryOpportunityStatus,
    ExitIntent,
    SignalEntryOpportunity,
    SignalFinality,
    StrategySignal,
    StructureStatus,
)
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


EXPECTED = {
    (EntryIntent.ALLOW, ExitIntent.HOLD): DirectiveKind.BUILD_ONLY_TO_RISK_TARGET,
    (EntryIntent.WATCH, ExitIntent.HOLD): DirectiveKind.KEEP_CURRENT,
    (EntryIntent.BLOCK, ExitIntent.HOLD): DirectiveKind.KEEP_CURRENT,
    (EntryIntent.NOT_EVALUATED, ExitIntent.HOLD): DirectiveKind.KEEP_CURRENT,
    **{
        (entry, ExitIntent.REDUCE): DirectiveKind.REDUCE_CURRENT_BY_FRACTION
        for entry in EntryIntent
    },
    **{(entry, ExitIntent.EXIT): DirectiveKind.FLAT for entry in EntryIntent},
    **{(entry, ExitIntent.NOT_EVALUATED): DirectiveKind.FREEZE for entry in EntryIntent},
}


@pytest.mark.parametrize("entry", list(EntryIntent))
@pytest.mark.parametrize("exit", list(ExitIntent))
def test_position_policy_truth_table(entry, exit):
    directive = decide_directive(entry, exit)
    assert directive.kind is EXPECTED[(entry, exit)]
    assert directive.fraction == (0.5 if exit is ExitIntent.REDUCE else None)


def _signal(code):
    return StrategySignal(
        signal_id=code,
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="test",
        parameter_fingerprint="test",
        code=code,
        occurred_on=date(2026, 10, 8),
        finality=SignalFinality.FINAL,
        direction=None,
        signal_price=Decimal("10"),
        evidence=[
            Evidence(
                code="signal",
                message="signal",
                observed_value=None,
                reference_value=None,
                importance=Importance.HIGH,
                source="test",
            )
        ],
        data_status=DataStatus.COMPLETE,
    )


def _opportunity(status, source_code="TREND_BREAKOUT_ENTRY"):
    return SignalEntryOpportunity(
        evaluation_as_of=date(2026, 10, 8),
        finality=SignalFinality.FINAL,
        status=status,
        entry_signal=_signal(source_code) if source_code is not None else None,
        invalidated_by=None,
        age_bars=None,
        signal_price=None,
        execution_reference_price=None,
        extension_pct=None,
        market_regime=None,
        structure_status=StructureStatus.UNKNOWN,
        evidence=[
            Evidence(
                code="opportunity",
                message="opportunity",
                observed_value=None,
                reference_value=None,
                importance=Importance.HIGH,
                source="test",
            )
        ],
        policy_version="test",
    )


@pytest.mark.parametrize(
    "higher,lower",
    [
        ("SMA150_EXIT", "OVERHEAT_CORRECTION"),
        ("OVERHEAT_CORRECTION", "POST_OVERHEAT_RECOVERY_ENTRY"),
        ("POST_OVERHEAT_RECOVERY_ENTRY", "PULLBACK_REVERSAL_ENTRY"),
        ("PULLBACK_REVERSAL_ENTRY", "TREND_BREAKOUT_ENTRY"),
        ("TREND_BREAKOUT_ENTRY", "DEEP_RECOVERY_ENTRY"),
    ],
)
def test_current_signal_priority_is_independent_of_list_order(higher, lower):
    from src.position import policy

    for codes in ((higher, lower), (lower, higher)):
        selected = policy.select_current_signal([_signal(code) for code in codes])
        assert selected.code == higher


@pytest.mark.parametrize("reverse", [False, True])
def test_current_signal_selects_latest_entry_before_type_priority(reverse):
    from src.position import policy

    older = _signal("POST_OVERHEAT_RECOVERY_ENTRY").model_copy(
        update={"occurred_on": date(2026, 10, 7)}
    )
    latest = _signal("DEEP_RECOVERY_ENTRY")
    signals = [older, latest]
    selected = policy.select_current_signal(signals[::-1] if reverse else signals)
    assert selected is latest


@pytest.mark.parametrize("code", ["SMA150_EXIT", "OVERHEAT_CORRECTION"])
def test_exit_or_correction_remains_prior_to_newer_entry(code):
    from src.position import policy

    safety = _signal(code).model_copy(update={"occurred_on": date(2026, 10, 7)})
    selected = policy.select_current_signal([_signal("POST_OVERHEAT_RECOVERY_ENTRY"), safety])
    assert selected is safety


@pytest.mark.parametrize("status", list(EntryOpportunityStatus))
def test_signal_entry_requires_allow_opportunity(status):
    from src.position import policy

    directive = policy.decide_signal_directive(
        [_signal("TREND_BREAKOUT_ENTRY")], _opportunity(status)
    )
    expected = (
        DirectiveKind.BUILD_ONLY_TO_RISK_TARGET
        if status is EntryOpportunityStatus.ALLOW
        else DirectiveKind.KEEP_CURRENT
    )
    assert directive.kind is expected


def test_allow_opportunity_without_current_signal_does_not_buy():
    from src.position import policy

    directive = policy.decide_signal_directive([], _opportunity(EntryOpportunityStatus.ALLOW))
    assert directive.kind is DirectiveKind.KEEP_CURRENT


def test_allow_opportunity_without_source_signal_does_not_buy():
    from src.position import policy

    directive = policy.decide_signal_directive(
        [_signal("TREND_BREAKOUT_ENTRY")],
        _opportunity(EntryOpportunityStatus.ALLOW, source_code=None),
    )
    assert directive.kind is DirectiveKind.KEEP_CURRENT


def test_allow_for_lower_priority_entry_does_not_authorize_selected_entry():
    from src.position import policy

    directive = policy.decide_signal_directive(
        [_signal("TREND_BREAKOUT_ENTRY"), _signal("PULLBACK_REVERSAL_ENTRY")],
        _opportunity(EntryOpportunityStatus.ALLOW),
    )
    assert directive.kind is DirectiveKind.KEEP_CURRENT


def test_matching_source_authorizes_selected_higher_priority_entry():
    from src.position import policy

    directive = policy.decide_signal_directive(
        [_signal("TREND_BREAKOUT_ENTRY"), _signal("PULLBACK_REVERSAL_ENTRY")],
        _opportunity(EntryOpportunityStatus.ALLOW, source_code="PULLBACK_REVERSAL_ENTRY"),
    )
    assert directive.kind is DirectiveKind.BUILD_ONLY_TO_RISK_TARGET


def test_same_code_with_different_signal_identity_does_not_buy():
    from src.position import policy

    opportunity = _opportunity(EntryOpportunityStatus.ALLOW)
    opportunity.entry_signal = opportunity.entry_signal.model_copy(
        update={"signal_id": "different-parameter-fingerprint-signal"}
    )
    directive = policy.decide_signal_directive([_signal("TREND_BREAKOUT_ENTRY")], opportunity)
    assert directive.kind is DirectiveKind.KEEP_CURRENT
