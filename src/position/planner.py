"""Compute order quantities from account state after policy and execution checks."""

import math
from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal

from src.position.models import (
    AccountSnapshot,
    DirectiveKind,
    EntryExecutionCheck,
    ExecutionResult,
    MarketSnapshot,
    PositionDirective,
    PositionPlan,
    PositionSnapshot,
    QuantityStatus,
)
from src.position.policy import decide_signal_directive, select_current_signal
from src.strategies.models import StrategySignalBundle, StrategyVerdict


def plan_position(
    verdict: StrategyVerdict,
    directive: PositionDirective,
    position: PositionSnapshot,
    account: AccountSnapshot | None,
    execution_check: EntryExecutionCheck | None,
) -> PositionPlan:
    """Preserve the Playbook API and its execution-pass requirement."""
    if directive.kind is DirectiveKind.BUILD_ONLY_TO_RISK_TARGET and (
        execution_check is None or execution_check.result is not ExecutionResult.PASS
    ):
        return _plan(directive, position.quantity, 0, 0)
    return _plan_directive(
        directive,
        position,
        account,
        execution_check.observed_open if execution_check is not None else None,
        execution_check.check_id if execution_check is not None else None,
    )


def plan_position_from_signals(
    bundle: StrategySignalBundle,
    position: PositionSnapshot,
    account: AccountSnapshot | None = None,
    market_snapshot: MarketSnapshot | None = None,
    *,
    calculated_at: datetime | None = None,
) -> PositionPlan:
    """Plan today's Signal with real holdings and a current price snapshot."""
    directive = decide_signal_directive(bundle.current_signals, bundle.entry_opportunity)
    selected = select_current_signal(bundle.current_signals)
    price = (
        market_snapshot.price
        if market_snapshot is not None and market_snapshot.session == bundle.as_of
        else None
    )
    plan = _plan_directive(directive, position, account, price)
    return replace(
        plan,
        signal_finality=selected.finality if selected else bundle.entry_opportunity.finality,
        calculated_at=calculated_at if calculated_at is not None else datetime.now(UTC),
        market_snapshot_hash=market_snapshot.snapshot_hash if market_snapshot is not None else None,
    )


def _plan_directive(
    directive: PositionDirective,
    position: PositionSnapshot,
    account: AccountSnapshot | None,
    price: Decimal | None,
    check_id: str | None = None,
) -> PositionPlan:
    current = position.quantity
    kind = directive.kind
    if kind is DirectiveKind.FLAT:
        return _plan(directive, current, 0, current)
    if kind is DirectiveKind.REDUCE_CURRENT_BY_FRACTION:
        if directive.fraction is None or not 0 <= directive.fraction <= 1:
            raise ValueError("reduce directive requires a fraction from zero to one")
        sell = math.ceil(current * directive.fraction)
        return _plan(directive, current, 0, sell)
    if kind in (DirectiveKind.KEEP_CURRENT, DirectiveKind.FREEZE):
        return _plan(directive, current, 0, 0)

    # Risk inputs belong to the real account, never to the chart Strategy.
    if (
        account is None
        or account.capital is None
        or account.risk_budget is None
        or account.per_share_risk is None
        or price is None
        or account.capital < 0
        or account.risk_budget < 0
        or account.per_share_risk <= 0
        or price <= 0
    ):
        return PositionPlan(
            directive=directive,
            current_quantity=current,
            target_quantity=None,
            buy_quantity=None,
            sell_quantity=None,
            quantity_status=QuantityStatus.UNAVAILABLE,
            execution_check_id=check_id,
        )
    risk_target = (account.risk_budget / account.per_share_risk).to_integral_value(
        rounding=ROUND_FLOOR
    )
    capital_target = (account.capital / price).to_integral_value(rounding=ROUND_FLOOR)
    target = int(min(risk_target, capital_target))
    return _plan(directive, current, max(target - current, 0), 0, check_id)


def _plan(
    directive: PositionDirective,
    current: int,
    buy: int,
    sell: int,
    check_id: str | None = None,
) -> PositionPlan:
    return PositionPlan(
        directive=directive,
        current_quantity=current,
        target_quantity=current + buy - sell,
        buy_quantity=buy,
        sell_quantity=sell,
        quantity_status=QuantityStatus.AVAILABLE,
        execution_check_id=check_id,
    )
