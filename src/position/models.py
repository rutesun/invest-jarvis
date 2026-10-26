"""Immutable position planning inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from src.strategies.models import SignalFinality


class DirectiveKind(StrEnum):
    BUILD_ONLY_TO_RISK_TARGET = "build_only_to_risk_target"
    KEEP_CURRENT = "keep_current"
    REDUCE_CURRENT_BY_FRACTION = "reduce_current_by_fraction"
    FLAT = "flat"
    FREEZE = "freeze"


class QuantityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ExecutionResult(StrEnum):
    PASS = "pass"
    STALE_SESSION = "stale_session"
    MISSING_MARKET_DATA = "missing_market_data"
    GAP_LIMIT_EXCEEDED = "gap_limit_exceeded"


@dataclass(frozen=True)
class PositionDirective:
    kind: DirectiveKind
    fraction: float | None = None


@dataclass(frozen=True)
class PositionSnapshot:
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("position quantity must be nonnegative")


@dataclass(frozen=True)
class AccountSnapshot:
    capital: Decimal | None
    risk_budget: Decimal | None
    per_share_risk: Decimal | None


@dataclass(frozen=True)
class MarketOpenSnapshot:
    session: date
    open_price: Decimal | None
    snapshot_hash: str


@dataclass(frozen=True)
class MarketSnapshot:
    """Current price observation used for same-session Signal planning."""

    session: date
    price: Decimal | None
    snapshot_hash: str


@dataclass(frozen=True)
class EntryExecutionCheck:
    check_id: str
    strategy_run_id: str
    source_event_id: str | None
    market_session: date
    market_snapshot_hash: str | None
    policy_version: str
    checked_at: datetime | None
    result: ExecutionResult
    observed_open: Decimal | None


@dataclass(frozen=True)
class PositionPlan:
    directive: PositionDirective
    current_quantity: int
    target_quantity: int | None
    buy_quantity: int | None
    sell_quantity: int | None
    quantity_status: QuantityStatus
    execution_check_id: str | None = None
    signal_finality: SignalFinality | None = None
    calculated_at: datetime | None = None
    market_snapshot_hash: str | None = None
