"""Causal execution and lot risk ledger for FINAL SWING_W150 V2 signals.

The detector owns chart signals. This module alone owns simulated quantities,
fills, stops and realized R; it never writes state back into strategy output.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import ROUND_FLOOR, Decimal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.storage.canonical import canonical_hash
from src.strategies.models import SignalFinality, StrategySignal
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import (
    SWING_W150_PARAMETER_REGISTRY,
    SwingW150Parameters,
)
from src.strategies.swing_w150.signals import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    iter_swing_detection,
)


_PRIORITY = (
    "SMA150_EXIT",
    "OVERHEAT_CORRECTION",
    "POST_OVERHEAT_RECOVERY_ENTRY",
    "PULLBACK_REVERSAL_ENTRY",
    "TREND_BREAKOUT_ENTRY",
    "DEEP_RECOVERY_ENTRY",
)
_ENTRIES = frozenset(_PRIORITY[2:])
_SUPPORTS = frozenset({"SMA_50", "SMA_150", "SMA_200", "SuperTrend_Up", "PRIOR_BREAKOUT_LEVEL"})


class SwingExecutionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = "SWING_EXECUTION_V2_1"
    fee_rate: float = Field(ge=0, lt=1, allow_inf_nan=False)
    slippage_rate: float = Field(ge=0, lt=1, allow_inf_nan=False)


class SwingRiskPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = "SWING_RISK_V2_1"
    risk_target: float = Field(gt=0, allow_inf_nan=False)
    trend_atr_multiplier: float = Field(default=3, gt=0, allow_inf_nan=False)
    stop_atr_multiplier: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    max_loss_pct: float = Field(default=0.15, gt=0, lt=1, allow_inf_nan=False)


@dataclass(frozen=True)
class SwingBacktestIdentity:
    ticker: str
    strategy_id: str
    strategy_version: str
    parameter_set_version: str
    parameter_fingerprint: str
    warmup_start: date
    test_start: date
    test_end: date
    execution_policy: SwingExecutionPolicy
    risk_policy: SwingRiskPolicy
    expected_sessions: tuple[date, ...]
    no_trade_sessions: tuple[date, ...]

    @property
    def identity_hash(self) -> str:
        payload = asdict(self)
        payload["execution_policy"] = self.execution_policy.model_dump()
        payload["risk_policy"] = self.risk_policy.model_dump()
        return canonical_hash("jarvis:swing-backtest:v2", payload)


@dataclass(frozen=True)
class SwingFill:
    date: date
    side: str
    reason: str
    price: float
    quantity: int
    fee: float
    lot_id: str
    signal_id: str | None


@dataclass(frozen=True)
class SwingLot:
    """Open residual or merged realized slices sharing the original lot basis.

    initial_quantity/risk_capital describe this slice's shares. The entry basis
    and initial_risk_per_share always remain those of the original buy fill.
    """

    lot_id: str
    signal_id: str
    entry_code: str
    entry_date: date
    entry_price: float
    stop: float
    initial_quantity: int
    quantity: int
    initial_risk_per_share: float
    initial_risk_capital: float
    entry_fee_per_share: float
    realized_pnl: float = 0
    exit_date: date | None = None


@dataclass(frozen=True)
class SwingBacktestResult:
    identity: SwingBacktestIdentity
    signal_history: tuple[StrategySignal, ...]
    orders: tuple[SwingFill, ...]
    open_lots: tuple[SwingLot, ...]
    closed_lots: tuple[SwingLot, ...]
    aggregate_r: float

    @property
    def trades(self) -> tuple[SwingLot, ...]:
        return self.closed_lots


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _initial_stop(
    signal: StrategySignal, row: pd.Series, entry: Decimal, policy: SwingRiskPolicy
) -> Decimal:
    def indicator(column: str) -> Decimal:
        value = row.get(column)
        if value is None or not math.isfinite(float(value)):
            raise ValueError(f"Missing finite stop input {column} for {signal.signal_id}")
        # Indicator libraries introduce sub-picocurrency float noise (e.g.
        # SMA=99.99999999999997 for constant 100), which must not remove a share
        # at an exact risk-budget boundary. Preserve twelve decimal places.
        return _decimal(float(value)).quantize(Decimal("0.000000000001"))

    atr = indicator("ATR")
    if atr <= 0:
        raise ValueError("ATR must be positive for entry execution")
    buffer = atr * _decimal(policy.stop_atr_multiplier)
    floor = entry * (1 - _decimal(policy.max_loss_pct))
    if signal.code == "TREND_BREAKOUT_ENTRY":
        return min(indicator("SMA_150"), entry - atr * _decimal(policy.trend_atr_multiplier))
    if signal.code == "DEEP_RECOVERY_ENTRY":
        return max(indicator("Low_20") - buffer, floor)
    if signal.code == "POST_OVERHEAT_RECOVERY_ENTRY":
        return max(indicator("SMA_20") - buffer, floor)
    supports = [
        _decimal(item.reference_value)
        for item in signal.evidence
        if item.code in _SUPPORTS
        and item.reference_value is not None
        and math.isfinite(item.reference_value)
    ]
    if not supports:
        raise ValueError(f"Missing pullback support evidence for {signal.signal_id}")
    # The detector confirms a reversal above the highest retained support.
    return max(max(supports) - buffer, floor)


class _Ledger:
    def __init__(self, execution: SwingExecutionPolicy, risk: SwingRiskPolicy):
        self.execution = execution
        self.risk = risk
        self.lots: list[SwingLot] = []
        self.closed: dict[str, SwingLot] = {}
        self.orders: list[SwingFill] = []

    def fill_price(self, raw_price: float, side: str) -> Decimal:
        adjustment = _decimal(self.execution.slippage_rate) * (1 if side == "buy" else -1)
        return _decimal(raw_price) * (1 + adjustment)

    def sell(
        self,
        index: int,
        quantity: int,
        raw_price: float,
        day: date,
        reason: str,
        signal_id: str | None = None,
    ) -> None:
        lot = self.lots[index]
        price = self.fill_price(raw_price, "sell")
        fee = price * quantity * _decimal(self.execution.fee_rate)
        pnl = (
            price - _decimal(lot.entry_price) - _decimal(lot.entry_fee_per_share)
        ) * quantity - fee
        remaining = lot.quantity - quantity
        previous = self.closed.get(lot.lot_id)
        realized_quantity = quantity + (previous.initial_quantity if previous else 0)
        realized_pnl = pnl + (_decimal(previous.realized_pnl) if previous else Decimal(0))
        self.closed[lot.lot_id] = replace(
            lot,
            initial_quantity=realized_quantity,
            quantity=0,
            initial_risk_capital=float(_decimal(lot.initial_risk_per_share) * realized_quantity),
            realized_pnl=float(realized_pnl),
            exit_date=day,
        )
        self.lots[index] = replace(
            lot,
            initial_quantity=remaining,
            quantity=remaining,
            initial_risk_capital=float(_decimal(lot.initial_risk_per_share) * remaining),
        )
        self.orders.append(
            SwingFill(
                day, "sell", reason, float(price), quantity, float(fee), lot.lot_id, signal_id
            )
        )

    def stops(self, row: pd.Series, day: date, *, gap_only: bool) -> None:
        for index, lot in enumerate(self.lots):
            if lot.quantity == 0:
                continue
            if row.Open <= lot.stop:
                self.sell(index, lot.quantity, float(row.Open), day, "gap_stop")
            elif not gap_only and row.Low <= lot.stop:
                self.sell(index, lot.quantity, lot.stop, day, "stop")

    def execute(
        self, signal: StrategySignal, signal_row: pd.Series, row: pd.Series, day: date
    ) -> None:
        quantity = sum(lot.quantity for lot in self.lots)
        if signal.code in {"SMA150_EXIT", "OVERHEAT_CORRECTION"}:
            to_sell = quantity if signal.code == "SMA150_EXIT" else (quantity + 1) // 2
            # FIFO assigns a partial exit deterministically without rebasing other lots.
            for index, lot in enumerate(self.lots):
                count = min(to_sell, lot.quantity)
                if count:
                    self.sell(index, count, float(row.Open), day, signal.code, signal.signal_id)
                    to_sell -= count
            return
        if signal.code not in _ENTRIES:
            return
        if quantity and signal.code != "POST_OVERHEAT_RECOVERY_ENTRY":
            return
        entry = self.fill_price(float(row.Open), "buy")
        stop = _initial_stop(signal, signal_row, entry, self.risk)
        per_share = entry - stop
        if stop <= 0 or per_share <= 0:
            raise ValueError(f"Invalid entry stop for {signal.signal_id}")
        existing_risk = sum(
            _decimal(lot.initial_risk_per_share) * lot.quantity for lot in self.lots
        )
        available = max(Decimal(0), _decimal(self.risk.risk_target) - existing_risk)
        count = int((available / per_share).to_integral_value(rounding=ROUND_FLOOR))
        if not count:
            return
        fee_per_share = entry * _decimal(self.execution.fee_rate)
        lot_id = f"{signal.signal_id}:lot:{len(self.lots) + 1}"
        self.lots.append(
            SwingLot(
                lot_id,
                signal.signal_id,
                signal.code,
                day,
                float(entry),
                float(stop),
                count,
                count,
                float(per_share),
                float(per_share * count),
                float(fee_per_share),
            )
        )
        self.orders.append(
            SwingFill(
                day,
                "buy",
                signal.code,
                float(entry),
                count,
                float(fee_per_share * count),
                lot_id,
                signal.signal_id,
            )
        )


def simulate_swing_v2(
    bars: pd.DataFrame,
    params: SwingW150Parameters,
    execution_policy: SwingExecutionPolicy,
    *,
    risk_policy: SwingRiskPolicy,
    warmup_start: date,
    test_start: date,
    test_end: date,
    ticker: str,
    expected_sessions: Sequence[date],
    no_trade_sessions: Sequence[date] = (),
    signal_history: Sequence[StrategySignal] | None = None,
) -> SwingBacktestResult:
    """Simulate the explicit inclusive test period, with no forced terminal sale.

    Stops use signal-day indicators and actual slipped entry prices. Risk target
    is a fixed currency amount; fees reduce realized PnL, not price-to-stop risk.
    A caller may supply chart-only signal history to execute an existing replay.
    Otherwise the public one-pass detector creates the same history as prefixes.
    Expected exchange sessions are independent of observed bars. Only explicitly
    declared no-trade sessions may have no bar; unexplained gaps abort the run.
    """
    if not warmup_start <= test_start <= test_end:
        raise ValueError("Invalid period: require warmup_start <= test_start <= test_end")
    SWING_W150_PARAMETER_REGISTRY.validate(params)
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("bars must have a DatetimeIndex")
    sessions = bars.index.date
    # Slice before indicators or validation: future OHLCV never enters computation.
    raw = bars.loc[(sessions >= warmup_start) & (sessions <= test_end)].copy()
    if raw.empty:
        raise ValueError("No instrument bars in requested period")
    sessions = raw.index.date
    if any(a >= b for a, b in zip(sessions, sessions[1:], strict=False)):
        raise ValueError("bars must have strictly ascending unique sessions")
    expected = tuple(day for day in expected_sessions if warmup_start <= day <= test_end)
    no_trade = tuple(day for day in no_trade_sessions if warmup_start <= day <= test_end)
    if not expected:
        raise ValueError("expected_sessions must cover the requested period")
    for name, days in (("expected_sessions", expected), ("no_trade_sessions", no_trade)):
        if any(a >= b for a, b in zip(days, days[1:], strict=False)):
            raise ValueError(f"{name} must be strictly ascending and unique")
    observed = set(sessions)
    if not set(no_trade).issubset(expected):
        raise ValueError("no_trade_sessions must be a subset of expected_sessions")
    if observed.intersection(no_trade):
        raise ValueError("observed bars and no_trade_sessions must be disjoint")
    if not observed.issubset(expected):
        raise ValueError("observed bars must belong to expected exchange sessions")
    missing = set(expected) - observed - set(no_trade)
    if missing:
        raise ValueError(f"Unaccounted exchange sessions: {sorted(missing)}")
    required = ("Open", "High", "Low", "Close", "Volume")
    if set(required) - set(raw.columns):
        raise ValueError("Missing OHLCV columns")
    if not all(math.isfinite(float(value)) for value in raw.loc[:, required].to_numpy().flat):
        raise ValueError("OHLCV must be finite within the requested period")
    if (raw.loc[:, required[:4]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    # A future fractional/NaN bar can change an entire pandas column's dtype.
    # Normalize only the clipped OHLCV so that it cannot change past evidence.
    raw = raw.loc[:, required].astype(float)
    features = build_swing_features(raw, params)
    if signal_history is None:
        history = tuple(
            signal
            for snapshot in iter_swing_detection(ticker, features, params)
            for signal in snapshot.current_signals
        )
    else:
        history = tuple(
            signal for signal in signal_history if warmup_start <= signal.occurred_on <= test_end
        )
    by_day: dict[date, list[StrategySignal]] = {}
    rows = {stamp.date(): row for stamp, row in features.frame.iterrows()}
    for signal in history:
        if signal.finality is not SignalFinality.FINAL:
            raise ValueError("Backtest requires FINAL signals in the input period")
        if (
            signal.strategy_id != STRATEGY_ID
            or signal.strategy_version != STRATEGY_VERSION
            or signal.parameter_set_version != params.parameter_set_version
            or signal.parameter_fingerprint != params.parameter_fingerprint
        ):
            raise ValueError("Signal identity does not match backtest parameters")
        if signal.occurred_on not in rows:
            raise ValueError("Signal date must have an actual instrument bar")
        if signal.occurred_on >= test_start:
            by_day.setdefault(signal.occurred_on, []).append(signal)
    ledger = _Ledger(execution_policy, risk_policy)
    pending: StrategySignal | None = None
    for day, row in rows.items():
        if day < test_start:
            continue
        ledger.stops(row, day, gap_only=True)
        if pending is not None:
            ledger.execute(pending, rows[pending.occurred_on], row, day)
        ledger.stops(row, day, gap_only=False)
        today = by_day.get(day, [])
        # Keep every signal in history, but execute only the highest-priority action.
        pending = next(
            (signal for code in _PRIORITY for signal in today if signal.code == code), None
        )
    identity = SwingBacktestIdentity(
        ticker,
        STRATEGY_ID,
        STRATEGY_VERSION,
        params.parameter_set_version,
        params.parameter_fingerprint,
        warmup_start,
        test_start,
        test_end,
        execution_policy,
        risk_policy,
        expected,
        no_trade,
    )
    closed = tuple(ledger.closed.values())
    initial_risk = sum(_decimal(lot.initial_risk_capital) for lot in closed)
    realized = sum(_decimal(lot.realized_pnl) for lot in closed)
    return SwingBacktestResult(
        identity,
        history,
        tuple(ledger.orders),
        tuple(lot for lot in ledger.lots if lot.quantity),
        closed,
        float(realized / initial_risk) if initial_risk else 0,
    )
