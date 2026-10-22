from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from src.position.models import (
    AccountSnapshot,
    DirectiveKind,
    EntryExecutionCheck,
    ExecutionResult,
    PositionDirective,
    PositionSnapshot,
    QuantityStatus,
)
from src.position.planner import plan_position
from src.strategies.models import (
    EntryIntent,
    EntryOpportunityStatus,
    ExitIntent,
    SignalEntryOpportunity,
    SignalFinality,
    StrategySignal,
    StrategySignalBundle,
    StructureStatus,
)
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


def _verdict(entry=EntryIntent.ALLOW, exit=ExitIntent.HOLD):
    from src.strategies.models import StrategyVerdict

    return StrategyVerdict.model_construct(
        strategy_id="PLAYBOOK_V1",
        as_of=date(2026, 10, 1),
        entry=type("Entry", (), {"intent": entry})(),
        exit=type("Exit", (), {"intent": exit})(),
    )


def _check(result=ExecutionResult.PASS):
    return EntryExecutionCheck(
        check_id="check",
        strategy_run_id="run",
        source_event_id=None,
        market_session=date(2026, 10, 2),
        market_snapshot_hash="market",
        policy_version="v1",
        checked_at=None,
        result=result,
        observed_open=Decimal("10"),
    )


@pytest.mark.parametrize("quantity,sell", [(0, 0), (1, 1), (2, 1), (3, 2), (5, 3)])
def test_reduce_sells_ceiling_half_and_never_buys(quantity, sell):
    plan = plan_position(
        _verdict(exit=ExitIntent.REDUCE),
        PositionDirective(DirectiveKind.REDUCE_CURRENT_BY_FRACTION, 0.5),
        PositionSnapshot(quantity),
        None,
        None,
    )
    assert (plan.sell_quantity, plan.buy_quantity, plan.target_quantity) == (
        sell,
        0,
        quantity - sell,
    )


def test_unheld_exit_sells_zero():
    plan = plan_position(
        _verdict(exit=ExitIntent.EXIT),
        PositionDirective(DirectiveKind.FLAT),
        PositionSnapshot(0),
        None,
        None,
    )
    assert (plan.sell_quantity, plan.target_quantity) == (0, 0)


@pytest.mark.parametrize("current,buy", [(0, 10), (8, 2), (10, 0), (12, 0)])
def test_build_only_buys_up_to_risk_target(current, buy):
    plan = plan_position(
        _verdict(),
        PositionDirective(DirectiveKind.BUILD_ONLY_TO_RISK_TARGET),
        PositionSnapshot(current),
        AccountSnapshot(
            capital=Decimal("1000"), risk_budget=Decimal("100"), per_share_risk=Decimal("10")
        ),
        _check(),
    )
    assert (plan.buy_quantity, plan.sell_quantity, plan.target_quantity) == (
        buy,
        0,
        current + buy,
    )


def test_missing_account_keeps_verdict_and_marks_quantity_unavailable():
    verdict = _verdict()
    plan = plan_position(
        verdict,
        PositionDirective(DirectiveKind.BUILD_ONLY_TO_RISK_TARGET),
        PositionSnapshot(4),
        None,
        _check(),
    )
    assert plan.quantity_status is QuantityStatus.UNAVAILABLE
    assert plan.buy_quantity is None
    assert verdict.entry.intent is EntryIntent.ALLOW


def test_failed_execution_check_prevents_build():
    plan = plan_position(
        _verdict(),
        PositionDirective(DirectiveKind.BUILD_ONLY_TO_RISK_TARGET),
        PositionSnapshot(1),
        AccountSnapshot(
            capital=Decimal("1000"), risk_budget=Decimal("100"), per_share_risk=Decimal("10")
        ),
        _check(ExecutionResult.GAP_LIMIT_EXCEEDED),
    )
    assert (plan.buy_quantity, plan.target_quantity) == (0, 1)


TODAY = date(2026, 10, 8)
CALCULATED_AT = datetime(2026, 10, 8, 10, tzinfo=UTC)


def _signal(code, day=TODAY, finality=SignalFinality.FINAL):
    return StrategySignal(
        signal_id=f"{day}:{code}",
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="test",
        parameter_fingerprint="test",
        code=code,
        occurred_on=day,
        finality=finality,
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


def _signal_bundle(history, status=EntryOpportunityStatus.ALLOW):
    finality = history[-1].finality if history else SignalFinality.FINAL
    entry = next((signal for signal in reversed(history) if signal.code.endswith("ENTRY")), None)
    return StrategySignalBundle(
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="test",
        parameter_fingerprint="test",
        ticker="AAPL",
        as_of=TODAY,
        observation_history=[],
        signal_history=history,
        current_signals=[signal for signal in history if signal.occurred_on == TODAY],
        entry_opportunity=SignalEntryOpportunity(
            evaluation_as_of=TODAY,
            finality=finality,
            status=status,
            entry_signal=entry,
            invalidated_by=None,
            age_bars=0 if entry else None,
            signal_price=entry.signal_price if entry else None,
            execution_reference_price=entry.signal_price if entry else None,
            extension_pct=Decimal("0") if entry else None,
            market_regime="bull",
            structure_status=StructureStatus.VALID,
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
        ),
        data_status=DataStatus.COMPLETE,
    )


def _signal_plan(bundle, quantity=0, price=Decimal("10"), session=TODAY, account=True):
    from src.position import models, planner

    return planner.plan_position_from_signals(
        bundle=bundle,
        position=PositionSnapshot(quantity),
        account=AccountSnapshot(
            capital=Decimal("1000"), risk_budget=Decimal("100"), per_share_risk=Decimal("10")
        )
        if account
        else None,
        market_snapshot=models.MarketSnapshot(
            session=session, price=price, snapshot_hash="current-market"
        ),
        calculated_at=CALCULATED_AT,
    )


@pytest.mark.parametrize("old_code", ["SMA150_EXIT", "OVERHEAT_CORRECTION"])
def test_old_exit_never_overrides_today_entry(old_code):
    bundle = _signal_bundle(
        [
            _signal(old_code, TODAY - timedelta(days=1)),
            _signal("TREND_BREAKOUT_ENTRY"),
        ]
    )
    plan = _signal_plan(bundle)
    assert plan.directive.kind is DirectiveKind.BUILD_ONLY_TO_RISK_TARGET
    assert (plan.buy_quantity, plan.sell_quantity) == (10, 0)


def test_same_day_exit_wins_over_entry():
    plan = _signal_plan(
        _signal_bundle(
            [
                _signal("SMA150_EXIT"),
                _signal("TREND_BREAKOUT_ENTRY"),
            ]
        ),
        quantity=5,
    )
    assert plan.directive.kind is DirectiveKind.FLAT
    assert (plan.sell_quantity, plan.buy_quantity, plan.target_quantity) == (5, 0, 0)


@pytest.mark.parametrize("exit_code", [None, "OVERHEAT_CORRECTION", "SMA150_EXIT"])
def test_cycle_termination_alone_does_not_exit_real_position(exit_code):
    from src.strategies.models import BarFinality, UpCycleState

    history = [_signal("TREND_BREAKOUT_ENTRY")]
    if exit_code:
        history.append(_signal(exit_code))
    bundle = _signal_bundle(history)
    bundle.up_cycle = UpCycleState(
        cycle_id="cycle",
        started_on=TODAY - timedelta(days=5),
        status="ACTIVE",
        status_as_of=TODAY,
        finality=BarFinality.FINAL,
    )
    active = _signal_plan(bundle, quantity=5)
    bundle.up_cycle = bundle.up_cycle.model_copy(
        update={
            "status": "TERMINATED",
            "terminated_on": TODAY,
            "terminal_reason": "SMA150_FAILURE",
        }
    )
    terminated = _signal_plan(bundle, quantity=5)
    assert terminated == active
    expected = {
        None: (DirectiveKind.BUILD_ONLY_TO_RISK_TARGET, 5, 0, 10),
        "OVERHEAT_CORRECTION": (DirectiveKind.REDUCE_CURRENT_BY_FRACTION, 0, 3, 2),
        "SMA150_EXIT": (DirectiveKind.FLAT, 0, 5, 0),
    }[exit_code]
    assert (
        terminated.directive.kind,
        terminated.buy_quantity,
        terminated.sell_quantity,
        terminated.target_quantity,
    ) == expected


@pytest.mark.parametrize("finality", list(SignalFinality))
def test_signal_calculates_snapshot_bound_quantity(finality):
    plan = _signal_plan(
        _signal_bundle([_signal("TREND_BREAKOUT_ENTRY", finality=finality)]), price=Decimal("200")
    )
    assert plan.signal_finality is finality
    assert plan.market_snapshot_hash == "current-market"
    assert plan.calculated_at == CALCULATED_AT
    assert (plan.buy_quantity, plan.target_quantity) == (5, 5)


@pytest.mark.parametrize(
    "code,quantity,sell,target",
    [
        ("OVERHEAT_CORRECTION", 5, 3, 2),
        ("OVERHEAT_CORRECTION", 0, 0, 0),
        ("SMA150_EXIT", 5, 5, 0),
        ("SMA150_EXIT", 0, 0, 0),
    ],
)
def test_sell_signal_uses_real_holding_even_without_account(code, quantity, sell, target):
    plan = _signal_plan(_signal_bundle([_signal(code)]), quantity=quantity, account=False)
    expected = (
        DirectiveKind.FLAT if code == "SMA150_EXIT" else DirectiveKind.REDUCE_CURRENT_BY_FRACTION
    )
    assert plan.directive.kind is expected
    assert (plan.sell_quantity, plan.buy_quantity, plan.target_quantity) == (sell, 0, target)


@pytest.mark.parametrize(
    "status",
    [status for status in EntryOpportunityStatus if status is not EntryOpportunityStatus.ALLOW],
)
def test_non_allow_opportunity_keeps_current_quantity(status):
    plan = _signal_plan(_signal_bundle([_signal("TREND_BREAKOUT_ENTRY")], status), quantity=4)
    assert (plan.buy_quantity, plan.sell_quantity, plan.target_quantity) == (0, 0, 4)


def test_historical_entry_opportunity_does_not_authorize_today_order():
    plan = _signal_plan(
        _signal_bundle([_signal("TREND_BREAKOUT_ENTRY", TODAY - timedelta(days=1))]), quantity=4
    )
    assert plan.directive.kind is DirectiveKind.KEEP_CURRENT
    assert (plan.buy_quantity, plan.sell_quantity, plan.target_quantity) == (0, 0, 4)


def test_current_entry_requires_opportunity_evaluated_for_today():
    bundle = _signal_bundle([_signal("TREND_BREAKOUT_ENTRY")])
    bundle.entry_opportunity = bundle.entry_opportunity.model_copy(
        update={"evaluation_as_of": TODAY - timedelta(days=1)}
    )
    plan = _signal_plan(bundle, quantity=4)
    assert plan.directive.kind is DirectiveKind.KEEP_CURRENT
    assert (plan.buy_quantity, plan.sell_quantity, plan.target_quantity) == (0, 0, 4)


def test_allow_for_different_same_day_entry_keeps_current_quantity():
    bundle = _signal_bundle([_signal("PULLBACK_REVERSAL_ENTRY"), _signal("TREND_BREAKOUT_ENTRY")])
    plan = _signal_plan(bundle, quantity=4)
    assert plan.directive.kind is DirectiveKind.KEEP_CURRENT
    assert (plan.buy_quantity, plan.sell_quantity, plan.target_quantity) == (0, 0, 4)


@pytest.mark.parametrize(
    "price,session,account",
    [
        (None, TODAY, True),
        (Decimal("0"), TODAY, True),
        (Decimal("10"), TODAY - timedelta(days=1), True),
        (Decimal("10"), TODAY, False),
    ],
)
def test_entry_with_missing_or_stale_inputs_marks_quantity_unavailable(price, session, account):
    plan = _signal_plan(
        _signal_bundle([_signal("TREND_BREAKOUT_ENTRY")]),
        price=price,
        session=session,
        account=account,
    )
    assert plan.quantity_status is QuantityStatus.UNAVAILABLE
    assert (plan.buy_quantity, plan.sell_quantity, plan.target_quantity) == (None, None, None)
