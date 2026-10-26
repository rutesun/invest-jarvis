"""Execution-time checks that leave the confirmed strategy verdict intact."""

from datetime import date, datetime
from decimal import Decimal

from src.position.models import EntryExecutionCheck, ExecutionResult, MarketOpenSnapshot
from src.storage.canonical import canonical_hash


def check_entry_execution(
    *,
    strategy_run_id: str,
    source_event_id: str | None,
    market_session: date,
    market: MarketOpenSnapshot | None,
    policy_version: str,
    reference_entry: Decimal | None = None,
    checked_at: datetime | None = None,
) -> EntryExecutionCheck:
    market_hash = market.snapshot_hash if market is not None else None
    check_id = canonical_hash(
        "jarvis:entry-execution-check:v1",
        {
            "strategy_run_id": strategy_run_id,
            "source_event_id": source_event_id,
            "market_session": market_session,
            "market_snapshot_hash": market_hash,
            "policy_version": policy_version,
        },
    )
    if market is None or market.open_price is None or market.open_price <= 0:
        result = ExecutionResult.MISSING_MARKET_DATA
    elif market.session != market_session:
        result = ExecutionResult.STALE_SESSION
    elif source_event_id is not None and (reference_entry is None or reference_entry <= 0):
        result = ExecutionResult.MISSING_MARKET_DATA
    elif source_event_id is not None and market.open_price > reference_entry * Decimal("1.05"):
        result = ExecutionResult.GAP_LIMIT_EXCEEDED
    else:
        result = ExecutionResult.PASS
    return EntryExecutionCheck(
        check_id=check_id,
        strategy_run_id=strategy_run_id,
        source_event_id=source_event_id,
        market_session=market_session,
        market_snapshot_hash=market_hash,
        policy_version=policy_version,
        checked_at=checked_at,
        result=result,
        observed_open=market.open_price if market is not None else None,
    )
