"""Shared chart-only strategy evaluation for check, analyze, and brief."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from src.pipelines.chart_analysis import ChartAnalysisService
from src.pipelines.quality_history import extend_quality_history, quality_history
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
from src.tools.technical.chart_analysis.models import (
    ChartAnalysis,
    ChartAnalysisResult,
    FactSelection,
)
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
    position_plans: dict[str, PositionPlan] = field(default_factory=dict)

    @property
    def quality_history(self) -> tuple[ChartAnalysisResult, ...]:
        return tuple(getattr(self.strategy_run, "quality_history", ()))

    @property
    def quality_history_unavailable(self) -> str | None:
        return getattr(self.strategy_run, "quality_history_unavailable", None)

    @property
    def common_analyses(self) -> dict[str, ChartAnalysis]:
        """Request-local facts without adding a serializable dataclass field."""
        return dict(getattr(self.strategy_run, "common_analyses", {}))

    @property
    def technical_fact_selections(self) -> tuple[FactSelection, ...]:
        """Original TechnicalResult decisions, excluded from legacy serialization."""
        return tuple(getattr(self.strategy_run, "technical_fact_selections", ()))

    @property
    def chart_analysis(self) -> ChartAnalysisResult | None:
        return getattr(self.strategy_run, "chart_analysis", None)

    @property
    def chart_analysis_unavailable(self) -> str | None:
        return getattr(self.strategy_run, "chart_analysis_unavailable", None)


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
        sessions = stock_sessions
        instrument_coverage = _coverage(
            stock_sessions, as_of, requested_start, "instrument_history_incomplete"
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
            as_of,
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
    as_of: date,
    requested_start: date,
    reason: str,
) -> CoverageManifest:
    # Coverage describes returned rows, not proof of exchange-wide completeness.
    # Strategy-specific minimum history and benchmark alignment remain downstream.
    complete = observed[-1] == as_of
    return CoverageManifest(
        requested_start=requested_start,
        actual_start=observed[0],
        actual_end=observed[-1],
        expected_sessions=tuple(day for day in observed if day >= requested_start),
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
        chart_service: ChartAnalysisService | None = None,
    ):
        self.chart_service = chart_service or ChartAnalysisService()
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
        # Strict Quality has its own canonical preparation. Existing inputs and
        # strategy/recorder fields remain untouched, including on input failure.
        history = ()
        history_unavailable = None
        try:
            raw = await quality_history(ticker, technical, bundle, self.chart_service, as_of)
            strict = (await self.chart_service.analyze(ticker, sessions=(as_of,), raw=raw))[0]
            run.chart_analysis = strict
            run.chart_analysis_unavailable = None
            # Five displayed sessions plus one prior observation for the first
            # daily delta. Reuse supplied prices; every date gets its own origin.
            sessions = tuple(
                raw.frame.index[raw.frame.index.date <= strict.analysis.manifest.as_of][-6:].date
            )
            try:
                origin = (pd.Timestamp(sessions[0]) - pd.DateOffset(years=2)).date()
                if self.chart_service.listing_first_session is not None:
                    origin = max(origin, self.chart_service.listing_first_session)
                history_raw = await extend_quality_history(
                    ticker, technical, raw, origin=origin, as_of=as_of
                )
                if history_raw is raw:
                    prior = await self.chart_service.analyze(
                        ticker, sessions=sessions[:-1], raw=raw
                    )
                    history = (*prior, strict)
                else:
                    # A successful history-only supplement changes provenance;
                    # keep all comparison points on that same verified input.
                    history = await self.chart_service.analyze(
                        ticker, sessions=sessions, raw=history_raw
                    )
                    run.chart_analysis = history[-1]
            except Exception as exc:
                history_unavailable = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            run.chart_analysis = None
            run.chart_analysis_unavailable = f"{type(exc).__name__}: {exc}"
        run.quality_history = history
        run.quality_history_unavailable = history_unavailable
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
        position_plans = {}
        if position is not None:
            for verdict in run.verdicts:
                position_plans[verdict.strategy_id] = _plan_verdict_position(
                    verdict, position, account, execution_check, as_of
                )
            for signals in getattr(run, "signal_bundles", ()):
                if signals.strategy_id == "SWING_W150":
                    position_plans[signals.strategy_id] = plan_position_from_signals(
                        signals, position, account, market_snapshot
                    )
            # Compatibility only: public renderers consume the keyed alternatives.
            position_plan = position_plans.get("SWING_W150") or position_plans.get("PLAYBOOK_V1")
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
            position_plans=position_plans,
            warning="; ".join(warnings) or None,
            score_history=tuple(getattr(technical, "score_history", ())),
            score_history_warning=getattr(technical, "score_history_warning", None),
        )


def _plan_verdict_position(
    selected,
    position: PositionSnapshot,
    account: AccountSnapshot | None,
    execution_check: EntryExecutionCheck | None,
    as_of: date,
) -> PositionPlan | None:
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
