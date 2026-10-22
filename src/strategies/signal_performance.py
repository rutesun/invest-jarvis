"""Pure, on-demand entry Signal performance; returns are Decimal ratios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.strategies.models import (
    BarFinality,
    ChartBundle,
    ReferenceEntryBasis,
    StrategySignal,
)
from src.tools.technical.scorecard_models import DataStatus


ENTRY_SIGNAL_CODES = frozenset(
    {
        "TREND_BREAKOUT_ENTRY",
        "DEEP_RECOVERY_ENTRY",
        "PULLBACK_REVERSAL_ENTRY",
        "POST_OVERHEAT_RECOVERY_ENTRY",
    }
)


@dataclass(frozen=True)
class SignalPerformance:
    signal_id: str
    strategy_id: str
    strategy_version: str
    parameter_set_version: str
    parameter_fingerprint: str
    signal_code: str
    signal_occurred_on: date
    ticker: str
    requested_as_of: date
    evaluation_as_of: date | None
    evaluation_price: Decimal | None
    signal_price: Decimal
    execution_reference_price: Decimal | None
    execution_as_of: date | None
    execution_delay_sessions: int | None
    estimated_return_from_signal_close: Decimal | None
    executed_return_from_next_tradable_open: Decimal | None
    estimated_price_basis: ReferenceEntryBasis
    executed_price_basis: ReferenceEntryBasis
    estimated_data_status: DataStatus
    executed_data_status: DataStatus
    estimated_status_reason: str
    executed_status_reason: str


def evaluate_signal_performance(
    signal: StrategySignal, bundle: ChartBundle, *, requested_as_of: date | None = None
) -> SignalPerformance:
    """Mark to the latest observed close without looking past the requested date."""
    requested = requested_as_of if requested_as_of is not None else bundle.as_of
    available = [bar for bar in bundle.instrument.bars if bar.session_date <= requested]
    evaluation = available[-1] if available else None
    source = next(
        (bar for bar in bundle.instrument.bars if bar.session_date == signal.occurred_on), None
    )
    estimated = executed = None
    execution_price = execution_date = delay = None
    estimated_status = executed_status = DataStatus.NOT_EVALUATED
    reason = (
        "EVALUATION_BAR_UNAVAILABLE"
        if evaluation is None
        else "NOT_ENTRY_SIGNAL"
        if signal.code not in ENTRY_SIGNAL_CODES
        else "INVALID_SIGNAL_PRICE"
        if signal.signal_price <= 0
        else "SIGNAL_BAR_UNAVAILABLE"
        if source is None
        else "SIGNAL_BAR_FINALITY_MISMATCH"
        if signal.finality.value != source.finality.value
        else "SIGNAL_AFTER_EVALUATION"
        if signal.occurred_on > evaluation.session_date
        else "INVALID_EVALUATION_PRICE"
        if evaluation.close <= 0
        else "SIGNAL_CLOSE_MISMATCH"
        if source.close != signal.signal_price
        else None
    )
    estimated_reason = executed_reason = reason or "NEXT_TRADABLE_BAR_UNAVAILABLE"
    if reason is None:
        provisional = evaluation.finality is BarFinality.PROVISIONAL
        metric_status = DataStatus.PARTIAL if provisional else DataStatus.COMPLETE
        estimated = evaluation.close / signal.signal_price - 1
        estimated_status = metric_status
        estimated_reason = (
            "PROVISIONAL_EVALUATION_CLOSE" if provisional else "FINAL_CLOSE_AVAILABLE"
        )
        next_bar = next(
            (
                bar
                for bar in bundle.instrument.bars
                if signal.occurred_on < bar.session_date <= evaluation.session_date
            ),
            None,
        )
        if next_bar is not None:
            skipped_sessions = {
                day
                for day in bundle.exchange_sessions
                if signal.occurred_on < day < next_bar.session_date
            }
            if next_bar.open <= 0:
                executed_reason = "INVALID_EXECUTION_PRICE"
            elif (
                signal.occurred_on not in bundle.exchange_sessions
                or next_bar.session_date not in bundle.exchange_sessions
            ):
                executed_reason = "EXECUTION_CALENDAR_UNAVAILABLE"
            elif not skipped_sessions.issubset(bundle.instrument.coverage.no_trade_sessions):
                executed_reason = "UNACCOUNTED_EXECUTION_SESSIONS"
            else:
                execution_price = next_bar.open
                execution_date = next_bar.session_date
                delay = len(skipped_sessions)
                executed = evaluation.close / execution_price - 1
                executed_status = metric_status
                executed_reason = (
                    "PROVISIONAL_EVALUATION_CLOSE"
                    if provisional
                    else "NEXT_TRADABLE_OPEN_AVAILABLE"
                )
    return SignalPerformance(
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        parameter_set_version=signal.parameter_set_version,
        parameter_fingerprint=signal.parameter_fingerprint,
        signal_code=signal.code,
        signal_occurred_on=signal.occurred_on,
        ticker=bundle.ticker,
        requested_as_of=requested,
        evaluation_as_of=evaluation.session_date if evaluation else None,
        evaluation_price=evaluation.close if evaluation else None,
        signal_price=signal.signal_price,
        execution_reference_price=execution_price,
        execution_as_of=execution_date,
        execution_delay_sessions=delay,
        estimated_return_from_signal_close=estimated,
        executed_return_from_next_tradable_open=executed,
        estimated_price_basis=ReferenceEntryBasis.SIGNAL_CLOSE_ESTIMATE,
        executed_price_basis=ReferenceEntryBasis.NEXT_OPEN_ACTUAL,
        estimated_data_status=estimated_status,
        executed_data_status=executed_status,
        estimated_status_reason=estimated_reason,
        executed_status_reason=executed_reason,
    )
