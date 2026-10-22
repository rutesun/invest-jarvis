"""Run the three production chart strategies with stable input identities."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.storage.canonical import canonical_hash, strategy_input_hash
from src.strategies.legacy_technical import LegacyTechnicalStrategy
from src.strategies.models import (
    ChartBundle,
    EntryIntent,
    EntryOpportunityStatus,
    EntryVerdict,
    ExitIntent,
    ExitVerdict,
    SignalEntryOpportunity,
    SignalFinality,
    StrategySignalBundle,
    StrategyVerdict,
    StructureStatus,
)
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.playbook import PlaybookStrategy
from src.strategies.swing_w150.adapter import SwingW150SignalStrategy
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.technical.models import TechnicalResult
from src.tools.technical.scorecard_models import (
    DataStatus,
    Evidence,
    Importance,
    TechnicalScorecard,
)


class StrategyRunBundle(BaseModel):
    ticker: str
    as_of: date
    input_data_hash: str
    strategy_versions: dict[str, str]
    chart_profile_version: str
    chart_bundle_hash: str
    strategy_input_hashes: dict[str, str]
    scorecard: TechnicalScorecard
    verdicts: list[StrategyVerdict]
    signal_bundles: list[StrategySignalBundle] = Field(default_factory=list)
    data_status: DataStatus
    errors: list[str]
    diagnostic_errors: list[str] = Field(default_factory=list)


class StrategyRunner:
    production_strategy_types = (
        LegacyTechnicalStrategy,
        PlaybookStrategy,
        SwingW150SignalStrategy,
    )
    production_strategy_ids = tuple(
        strategy_type.strategy_id for strategy_type in production_strategy_types
    )

    def __init__(
        self,
        cache: Any = None,
        *,
        shadow_enabled: bool = True,
        observations_enabled: bool = True,
        observation_parameters: ObservationParameters | None = None,
        swing_parameters: SwingW150Parameters | None = None,
    ):
        # Chart strategies always recompute from their supplied chart.
        self._cache = cache
        self._strategies = tuple(
            strategy_type(
                params=swing_parameters,
                shadow_enabled=shadow_enabled,
                observations_enabled=observations_enabled,
                observation_parameters=observation_parameters,
            )
            if strategy_type is SwingW150SignalStrategy
            else strategy_type()
            for strategy_type in self.production_strategy_types
        )

    def production_strategy_registry(self) -> dict[str, str]:
        return {strategy.strategy_id: strategy.strategy_version for strategy in self._strategies}

    def run(self, bundle: ChartBundle, *, legacy_result: TechnicalResult) -> StrategyRunBundle:
        scorecard = legacy_result.scorecard
        if scorecard is None:
            raise ValueError("scorecard is required")
        if scorecard.ticker != bundle.ticker:
            raise ValueError("scorecard ticker must match ChartBundle ticker")
        if scorecard.as_of != bundle.as_of:
            raise ValueError("scorecard as_of must match ChartBundle as_of")

        strategies = self._strategies
        verdicts = []
        signal_bundles = []
        errors = []
        for strategy in strategies:
            try:
                if isinstance(strategy, SwingW150SignalStrategy):
                    signals = strategy.evaluate_signals(bundle)
                    if signals.strategy_id != strategy.strategy_id:
                        raise ValueError("Strategy returned a different identity")
                    signal_bundles.append(signals)
                    continue
                verdict = strategy.evaluate(bundle)
                if verdict.strategy_id != strategy.strategy_id:
                    raise ValueError("Strategy returned a different identity")
                verdicts.append(verdict)
            except Exception as exc:
                errors.append(f"{strategy.strategy_id}: {type(exc).__name__}: {exc}")
                if isinstance(strategy, SwingW150SignalStrategy):
                    signal_bundles.append(self._error_signal_bundle(bundle, strategy, exc))
                else:
                    verdicts.append(self._error_verdict(bundle, strategy, exc))

        statuses = [
            status
            for verdict in verdicts
            for status in (verdict.entry.data_status, verdict.exit.data_status)
        ]
        statuses.extend(signals.data_status for signals in signal_bundles)
        if DataStatus.ERROR in statuses:
            overall = DataStatus.ERROR
        elif DataStatus.INSUFFICIENT_DATA in statuses:
            overall = DataStatus.INSUFFICIENT_DATA
        elif DataStatus.PARTIAL in statuses:
            overall = DataStatus.PARTIAL
        else:
            overall = DataStatus.COMPLETE

        versions = self.production_strategy_registry()
        hashes = {
            strategy.strategy_id: strategy_input_hash(
                bundle,
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                parameter_fingerprint=(
                    strategy.parameters.parameter_fingerprint
                    if isinstance(strategy, SwingW150SignalStrategy)
                    else None
                ),
            )
            for strategy in strategies
        }
        return StrategyRunBundle(
            ticker=bundle.ticker,
            as_of=bundle.as_of,
            input_data_hash=canonical_hash(
                "jarvis:strategy-run-input:v1",
                {"chart_bundle_hash": bundle.bundle_hash, "strategy_input_hashes": hashes},
            ),
            strategy_versions=versions,
            chart_profile_version=bundle.profile_version,
            chart_bundle_hash=bundle.bundle_hash,
            strategy_input_hashes=hashes,
            scorecard=scorecard,
            verdicts=verdicts,
            signal_bundles=signal_bundles,
            data_status=overall,
            errors=errors,
            diagnostic_errors=[
                f"{signals.strategy_id}: {message}"
                for signals in signal_bundles
                for message in signals.diagnostic_errors
            ],
        )

    @staticmethod
    def _error_signal_bundle(bundle, strategy, exc: Exception) -> StrategySignalBundle:
        reason = Evidence(
            code="strategy_error",
            message=f"{type(exc).__name__}: {exc}",
            observed_value=None,
            reference_value=None,
            importance=Importance.HIGH,
            source=strategy.strategy_id,
        )
        finality = SignalFinality(bundle.instrument.bars[-1].finality.value)
        return StrategySignalBundle(
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            parameter_set_version=strategy.parameters.parameter_set_version,
            parameter_fingerprint=strategy.parameters.parameter_fingerprint,
            ticker=bundle.ticker,
            as_of=bundle.as_of,
            observation_history=[],
            signal_history=[],
            current_signals=[],
            entry_opportunity=SignalEntryOpportunity(
                evaluation_as_of=bundle.as_of,
                finality=finality,
                status=EntryOpportunityStatus.NOT_EVALUATED,
                entry_signal=None,
                invalidated_by=None,
                age_bars=None,
                signal_price=None,
                execution_reference_price=None,
                extension_pct=None,
                market_regime=None,
                structure_status=StructureStatus.UNKNOWN,
                evidence=[reason],
                policy_version=strategy.parameters.parameter_set_version,
            ),
            data_status=DataStatus.ERROR,
        )

    @staticmethod
    def _error_verdict(bundle, strategy, exc: Exception) -> StrategyVerdict:
        reason = Evidence(
            code="strategy_error",
            message=f"{type(exc).__name__}: {exc}",
            observed_value=None,
            reference_value=None,
            importance=Importance.HIGH,
            source=strategy.strategy_id,
        )
        return StrategyVerdict(
            verdict_schema_version="1",
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            ticker=bundle.ticker,
            as_of=bundle.as_of,
            entry=EntryVerdict(
                intent=EntryIntent.NOT_EVALUATED,
                opportunity=None,
                data_status=DataStatus.ERROR,
                reasons=[reason],
            ),
            exit=ExitVerdict(
                intent=ExitIntent.NOT_EVALUATED,
                data_status=DataStatus.ERROR,
                reasons=[reason],
            ),
            events=[],
            strategy_state=None,
        )
