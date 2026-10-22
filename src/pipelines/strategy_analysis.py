"""Shared chart-only strategy evaluation for check, analyze, and brief."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from src.position.models import (
    AccountSnapshot,
    DirectiveKind,
    EntryExecutionCheck,
    ExecutionResult,
    MarketSnapshot,
    PositionPlan,
    PositionSnapshot,
    QuantityStatus,
)
from src.position.planner import plan_position, plan_position_from_signals
from src.position.policy import decide_directive
from src.providers.exchange_calendar import exchange_sessions_for
from src.providers.yfinance_provider import YFinanceProvider
from src.storage.entry_shadow import EntryShadowJsonlRecorder
from src.strategies.chart_bundle import chart_bundle_from_dataframes
from src.strategies.models import ChartBundle, CoverageManifest
from src.strategies.runner import StrategyRunBundle, StrategyRunner
from src.strategies.signal_performance import (
    ENTRY_SIGNAL_CODES,
    SignalPerformance,
    evaluate_signal_performance,
)
from src.tools.disclosure import is_korean_ticker
from src.tools.technical.models import ScoreHistoryPoint, TechnicalResult
from src.tools.technical.scorecard_models import TechnicalScorecard


logger = logging.getLogger(__name__)
_DEFAULT_SHADOW_RECORDER = object()


@dataclass(frozen=True)
class AnalysisStrategyResult:
    scorecard: TechnicalScorecard
    strategy_run: StrategyRunBundle
    exchange_sessions: tuple[date, ...]
    current_close: float
    position_plan: PositionPlan | None = None
    warning: str | None = None
    signal_performances: tuple[SignalPerformance, ...] = ()
    score_history: tuple[ScoreHistoryPoint, ...] = ()
    score_history_warning: str | None = None


class ChartBundleLoader:
    """Complete a technical price frame with an independently fetched market chart."""

    def __init__(self, market_provider: Any | None = None):
        self.market_provider = market_provider or YFinanceProvider()

    async def load(
        self,
        *,
        ticker: str,
        technical: TechnicalResult,
        as_of: date,
        observed_at: datetime | None = None,
    ) -> ChartBundle:
        instrument = _through(technical.raw_dataframe, as_of)
        if instrument.empty:
            raise ValueError("instrument OHLCV is unavailable")
        stock_sessions = tuple(pd.Timestamp(day).date() for day in instrument.index)
        requested_start = as_of - timedelta(days=365 * 2)
        calendar_name = "XKRX" if is_korean_ticker(ticker) else "XNYS"
        sessions = exchange_sessions_for(calendar_name, requested_start, as_of)
        if not sessions:
            raise ValueError("exchange calendar has no sessions in the requested period")
        instrument_coverage = _coverage(
            stock_sessions, sessions, requested_start, "instrument_history_incomplete"
        )
        market_ticker = _market_ticker(ticker)
        try:
            market = _through(
                await self.market_provider.get_price_history(market_ticker, "2y"), as_of
            )
        except Exception as exc:
            logger.warning("Market chart unavailable for %s (%s): %s", ticker, market_ticker, exc)
            market = None
        if market is None or market.empty:
            return chart_bundle_from_dataframes(
                profile_version="CHART_PROFILE_V1",
                ticker=ticker,
                as_of=as_of,
                instrument=instrument,
                instrument_coverage=instrument_coverage,
                exchange_sessions=sessions,
                observed_at=observed_at or getattr(technical, "timestamp", None),
            )

        market_coverage = _coverage(
            tuple(pd.Timestamp(day).date() for day in market.index),
            sessions,
            requested_start,
            "market_history_incomplete",
        )
        return chart_bundle_from_dataframes(
            profile_version="CHART_PROFILE_V1",
            ticker=ticker,
            as_of=as_of,
            instrument=instrument,
            instrument_coverage=instrument_coverage,
            exchange_sessions=sessions,
            market=market,
            market_coverage=market_coverage,
            market_ticker=market_ticker,
            observed_at=observed_at or getattr(technical, "timestamp", None),
        )


def _coverage(
    observed: tuple[date, ...],
    expected: tuple[date, ...],
    requested_start: date,
    reason: str,
) -> CoverageManifest:
    missing = set(expected) - set(observed)
    effective_start = None
    # period=2y may omit exactly one leading session at its rolling boundary.
    # Accept it only when every subsequent exchange session through as_of exists.
    if (
        len(expected) > 1
        and missing == {expected[0]}
        and observed[0] == expected[1]
        and observed[-1] == expected[-1]
    ):
        effective_start = expected[1]
        expected = expected[1:]
        missing = set()
    complete = not missing and observed[-1] == expected[-1]
    return CoverageManifest(
        requested_start=requested_start,
        effective_start=effective_start,
        actual_start=observed[0],
        actual_end=observed[-1],
        expected_sessions=expected,
        complete=complete,
        truncation_reason=None if complete else reason,
        # The first observed bar is not a verified listing date or suspension.
        listing_first_session=None,
    )


def _through(frame: pd.DataFrame, as_of: date) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.loc[[pd.Timestamp(index).date() <= as_of for index in frame.index]].sort_index()


def _market_ticker(ticker: str) -> str:
    if ticker.endswith(".KQ"):
        return "^KQ11"
    if is_korean_ticker(ticker):
        return "^KS11"
    return "SPY"


class AnalysisStrategyService:
    def __init__(
        self,
        chart_loader: ChartBundleLoader | None = None,
        strategy_runner: StrategyRunner | None = None,
        *,
        shadow_recorder: EntryShadowJsonlRecorder | None | object = _DEFAULT_SHADOW_RECORDER,
    ):
        self.chart_loader = chart_loader or ChartBundleLoader()
        self.strategy_runner = strategy_runner or StrategyRunner()
        # Explicit None disables recording; omission enables local research snapshots.
        self.shadow_recorder = (
            EntryShadowJsonlRecorder(
                Path(
                    os.environ.get(
                        "JARVIS_ENTRY_SHADOW_LOG_PATH", "data/research/entry-shadow.jsonl"
                    )
                )
            )
            if shadow_recorder is _DEFAULT_SHADOW_RECORDER
            else shadow_recorder
        )

    async def evaluate(
        self,
        ticker: str,
        technical: TechnicalResult,
        *,
        as_of: date,
        position_plan: PositionPlan | None = None,
        position: PositionSnapshot | None = None,
        account: AccountSnapshot | None = None,
        execution_check: EntryExecutionCheck | None = None,
        market_snapshot: MarketSnapshot | None = None,
        pipeline: str = "check",
    ) -> AnalysisStrategyResult:
        bundle = await self.chart_loader.load(ticker=ticker, technical=technical, as_of=as_of)
        run = self.strategy_runner.run(bundle, legacy_result=technical)
        warnings = []
        if bundle.market is None:
            warnings.append("Market chart unavailable; strategy coverage is incomplete")
        if self.shadow_recorder is not None:
            try:
                self.shadow_recorder.record(run, bundle, pipeline=pipeline)
            except Exception as exc:
                warning = f"Shadow 기록 실패: {type(exc).__name__}: {exc}"
                logger.warning("%s: %s", ticker, warning)
                warnings.append(warning)
        if position is not None:
            signals = next(
                (
                    signals
                    for signals in getattr(run, "signal_bundles", [])
                    if signals.strategy_id == "SWING_W150"
                ),
                None,
            )
            position_plan = (
                plan_position_from_signals(signals, position, account, market_snapshot)
                if signals is not None
                else _plan_playbook_position(run, position, account, execution_check, as_of)
            )
        return AnalysisStrategyResult(
            scorecard=run.scorecard,
            strategy_run=run,
            exchange_sessions=bundle.exchange_sessions,
            current_close=float(bundle.instrument.bars[-1].close),
            signal_performances=tuple(
                evaluate_signal_performance(signal, bundle, requested_as_of=as_of)
                for signal_bundle in getattr(run, "signal_bundles", [])
                for signal in signal_bundle.signal_history
                if signal.code in ENTRY_SIGNAL_CODES
            ),
            position_plan=position_plan,
            warning="; ".join(warnings) or None,
            score_history=tuple(getattr(technical, "score_history", ())),
            score_history_warning=getattr(technical, "score_history_warning", None),
        )


def _plan_playbook_position(
    run: StrategyRunBundle,
    position: PositionSnapshot,
    account: AccountSnapshot | None,
    execution_check: EntryExecutionCheck | None,
    as_of: date,
) -> PositionPlan | None:
    selected = next(
        (verdict for verdict in run.verdicts if verdict.strategy_id == "PLAYBOOK_V1"), None
    )
    if selected is None:
        return None
    directive = decide_directive(selected.entry.intent, selected.exit.intent)
    plan = plan_position(selected, directive, position, account, execution_check)
    if directive.kind is DirectiveKind.BUILD_ONLY_TO_RISK_TARGET and (
        execution_check is None
        or execution_check.result is not ExecutionResult.PASS
        or execution_check.market_session <= as_of
    ):
        return replace(
            plan,
            target_quantity=None,
            buy_quantity=None,
            sell_quantity=None,
            quantity_status=QuantityStatus.UNAVAILABLE,
        )
    return plan


def account_from_capital(capital: float | None, risk_pct: float | None) -> AccountSnapshot | None:
    if capital is None and risk_pct is None:
        return None
    amount = Decimal(str(capital)) if capital is not None else None
    risk_budget = (
        amount * Decimal(str(risk_pct)) if amount is not None and risk_pct is not None else None
    )
    return AccountSnapshot(capital=amount, risk_budget=risk_budget, per_share_risk=None)


async def evaluate_optional(
    service: AnalysisStrategyService | None,
    ticker: str,
    technical: TechnicalResult,
    *,
    position: PositionSnapshot | None = None,
    account: AccountSnapshot | None = None,
    execution_check: EntryExecutionCheck | None = None,
    market_snapshot: MarketSnapshot | None = None,
    pipeline: str = "check",
) -> tuple[AnalysisStrategyResult | None, str | None]:
    if service is None:
        return None, "Strategy section unavailable: analysis service is not configured"
    if technical.scorecard is None:
        return None, "Strategy section unavailable: technical scorecard is missing"
    try:
        result = await service.evaluate(
            ticker,
            technical,
            as_of=technical.scorecard.as_of,
            position=position,
            account=account,
            execution_check=execution_check,
            market_snapshot=market_snapshot,
            pipeline=pipeline,
        )
        return result, result.warning
    except Exception as exc:
        warning = f"Strategy section unavailable: {type(exc).__name__}: {exc}"
        logger.warning("%s: %s", ticker, warning)
        return None, warning
