"""Chart-only SWING_W150 verdict adapter."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pandas as pd

from src.storage.canonical import canonical_hash
from src.strategies.entry_anchors import build_entry_source_anchors
from src.strategies.entry_opportunity import (
    evaluate_entry_opportunity,
    evaluate_signal_entry_opportunity,
)
from src.strategies.entry_shadow import EntryShadowParameters, evaluate_entry_shadow
from src.strategies.models import (
    ChartBundle,
    EntryIntent,
    EntryOpportunityStatus,
    EntryVerdict,
    ExitIntent,
    ExitVerdict,
    ObservationSourceContext,
    StrategyEvent,
    StrategySignalBundle,
    StrategyVerdict,
)
from src.strategies.observations.detectors import evaluate_observations
from src.strategies.observations.parameters import (
    PRODUCT_OBSERVATION_PARAMETERS,
    ObservationParameters,
)
from src.strategies.swing_w150.engine import replay_trace
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import SwingW150Parameters, validate_pullback_policy
from src.strategies.swing_w150.rules import WARMUP_BARS
from src.strategies.swing_w150.signals import detect_swing
from src.tools.technical.scorecard_models import DataStatus, Direction, Evidence, Importance


def _frame(bundle: ChartBundle) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [float(bar.open) for bar in bundle.instrument.bars],
            "High": [float(bar.high) for bar in bundle.instrument.bars],
            "Low": [float(bar.low) for bar in bundle.instrument.bars],
            "Close": [float(bar.close) for bar in bundle.instrument.bars],
            "Volume": [float(bar.volume) for bar in bundle.instrument.bars],
        },
        index=pd.DatetimeIndex([bar.session_date for bar in bundle.instrument.bars]),
    )


def _origin(bundle: ChartBundle) -> date | None:
    cutoff = (pd.Timestamp(bundle.as_of) - pd.DateOffset(years=3)).date()
    listing = bundle.instrument.coverage.listing_first_session
    start = max(cutoff, listing) if listing is not None else cutoff
    return next((day for day in bundle.exchange_sessions if day >= start), None)


class SwingW150SignalStrategy:
    strategy_id = "SWING_W150"
    strategy_version = "SWING_W150_V2"

    def __init__(
        self,
        params: SwingW150Parameters | None = None,
        *,
        shadow_enabled: bool = True,
        shadow_parameters: EntryShadowParameters | None = None,
        observations_enabled: bool = True,
        observation_parameters: ObservationParameters | None = None,
    ) -> None:
        self.parameters = params or SwingW150Parameters()
        validate_pullback_policy(self.parameters)
        self.shadow_enabled = shadow_enabled
        self.shadow_parameters = shadow_parameters or EntryShadowParameters()
        self.observations_enabled = observations_enabled
        self.observation_parameters = observation_parameters or PRODUCT_OBSERVATION_PARAMETERS

    def evaluate_signals(self, bundle: ChartBundle) -> StrategySignalBundle:
        features = build_swing_features(
            _frame(bundle),
            self.parameters,
            finalities=[bar.finality for bar in bundle.instrument.bars],
            coverage=bundle.instrument.coverage,
        )
        detection = detect_swing(bundle.ticker, features, self.parameters)
        opportunity = evaluate_signal_entry_opportunity(
            detection.signal_history, bundle, self.parameters, features=features
        )
        diagnostic_errors = []
        if opportunity.entry_signal is not None:
            try:
                anchors = build_entry_source_anchors(
                    opportunity.entry_signal, bundle, features, detection.observation_history
                )
                opportunity = opportunity.model_copy(update={"anchors": anchors})
            except Exception as exc:
                diagnostic_errors.append(f"entry_anchors: {type(exc).__name__}: {exc}")
        shadow = None
        if self.shadow_enabled:
            try:
                shadow = evaluate_entry_shadow(opportunity, bundle, params=self.shadow_parameters)
            except Exception as exc:
                diagnostic_errors.append(f"entry_shadow: {type(exc).__name__}: {exc}")
        observations = detection.observation_history
        if self.observations_enabled:
            try:
                entry_codes = {
                    "TREND_BREAKOUT_ENTRY",
                    "DEEP_RECOVERY_ENTRY",
                    "PULLBACK_REVERSAL_ENTRY",
                    "POST_OVERHEAT_RECOVERY_ENTRY",
                }
                non_entries = [
                    item for item in detection.signal_history if item.code not in entry_codes
                ]
                contexts = []
                for source in detection.signal_history:
                    if source.code not in entry_codes:
                        continue
                    source_opportunity = evaluate_signal_entry_opportunity(
                        [source, *non_entries], bundle, self.parameters, features=features
                    )
                    source_anchors = None
                    try:
                        source_anchors = (
                            opportunity.anchors
                            if source == opportunity.entry_signal
                            else build_entry_source_anchors(
                                source, bundle, features, detection.observation_history
                            )
                        )
                    except Exception as exc:
                        diagnostic_errors.append(
                            f"observation_anchors[{source.signal_id}]: {type(exc).__name__}: {exc}"
                        )
                    terminal = source_opportunity.status in {
                        EntryOpportunityStatus.INVALIDATED,
                        EntryOpportunityStatus.EXPIRED,
                    }
                    contexts.append(
                        ObservationSourceContext(
                            signal=source,
                            anchors=source_anchors,
                            terminal_status=source_opportunity.status if terminal else None,
                            terminal_on=source_opportunity.terminal_on if terminal else None,
                            terminal_reason=(
                                source_opportunity.invalidated_by.code
                                if source_opportunity.invalidated_by is not None
                                else source_opportunity.evidence[0].code
                                if terminal
                                else None
                            ),
                        )
                    )
                observations = evaluate_observations(
                    bundle.ticker,
                    features,
                    detection.signal_history,
                    observations,
                    source_contexts=contexts,
                    params=self.observation_parameters,
                )
            except Exception as exc:
                diagnostic_errors.append(f"observations: {type(exc).__name__}: {exc}")
        return StrategySignalBundle(
            strategy_id=detection.strategy_id,
            strategy_version=detection.strategy_version,
            parameter_set_version=detection.parameter_set_version,
            parameter_fingerprint=detection.parameter_fingerprint,
            ticker=detection.ticker,
            as_of=detection.as_of,
            observation_history=observations,
            signal_history=detection.signal_history,
            current_signals=detection.current_signals,
            entry_opportunity=opportunity,
            data_status=detection.data_status,
            entry_shadow=shadow,
            diagnostic_errors=diagnostic_errors,
            up_cycle=detection.up_cycle,
            support_tests=detection.support_tests,
            pullback_policy_inactive_reason=detection.pullback_policy_inactive_reason,
            observations_enabled=self.observations_enabled,
            observation_parameters=asdict(self.observation_parameters),
        )


class SwingW150Strategy:
    strategy_id = "SWING_W150"
    strategy_version = "SWING_W150_V1"

    def evaluate(self, bundle: ChartBundle) -> StrategyVerdict:
        origin = _origin(bundle)
        cutoff = (pd.Timestamp(bundle.as_of) - pd.DateOffset(years=3)).date()
        manifest = bundle.instrument.coverage
        covered = (
            origin is not None
            and manifest.complete
            and manifest.truncation_reason is None
            and (
                manifest.actual_start <= cutoff
                or manifest.listing_first_session == manifest.actual_start
            )
            and (
                manifest.requested_start <= cutoff
                or manifest.listing_first_session == manifest.actual_start
            )
            and bundle.has_complete_coverage(origin, bundle.as_of)
        )
        if not covered:
            return self._verdict(
                bundle,
                EntryIntent.NOT_EVALUATED,
                ExitIntent.NOT_EVALUATED,
                DataStatus.INSUFFICIENT_DATA,
            )
        prefix = bundle.prefix(bundle.as_of, origin=origin)
        if len(prefix.instrument.bars) <= WARMUP_BARS:
            return self._verdict(
                bundle,
                EntryIntent.NOT_EVALUATED,
                ExitIntent.NOT_EVALUATED,
                DataStatus.INSUFFICIENT_DATA,
            )

        trace = replay_trace(_frame(prefix))
        dated_events = []
        recent_sessions = set(prefix.exchange_sessions[-21:])
        for item in trace.events:
            day = prefix.instrument.bars[item.index].session_date
            if day not in recent_sessions:
                continue
            evidence = []
            for code, value in (("reference_entry", item.entry), ("reference_stop", item.stop)):
                if value is not None:
                    evidence.append(
                        Evidence(
                            code=code,
                            message=code,
                            observed_value=value,
                            reference_value=None,
                            importance=Importance.MEDIUM,
                            source=self.strategy_id,
                        )
                    )
            dated_events.append(
                StrategyEvent(
                    event_id=canonical_hash(
                        "jarvis:swing-event:v1",
                        {
                            "ticker": bundle.ticker,
                            "day": day,
                            "code": item.code,
                            "version": self.strategy_version,
                        },
                    ),
                    code=item.code,
                    event_version=self.strategy_version,
                    occurred_on=day,
                    direction=(
                        Direction.RISING
                        if item.code.endswith("ENTRY")
                        or item.code in {"OVERHEAT_REBUY", "D_GRADUATION"}
                        else Direction.FALLING
                    ),
                    evidence=evidence,
                )
            )
        today_codes = {event.code for event in dated_events if event.occurred_on == bundle.as_of}
        state = trace.state
        source = next(
            (event for event in reversed(dated_events) if event.code in {"S_ENTRY", "D_ENTRY"}),
            None,
        )
        result = evaluate_entry_opportunity(source, prefix, bundle.as_of) if source else None
        opportunity = result.opportunity if result else None
        if today_codes.intersection({"STOP", "SMA150_EXIT", "OVERHEAT_SELL"}):
            entry, exit_ = EntryIntent.BLOCK, ExitIntent.EXIT
        elif "OVERHEAT_REBUY" in today_codes:
            entry, exit_ = EntryIntent.ALLOW, ExitIntent.HOLD
        elif result is not None:
            entry = result.intent
            exit_ = ExitIntent.EXIT if state.cycle_phase == "awaiting_rebuy" else ExitIntent.HOLD
        elif state.cycle_phase == "awaiting_rebuy":
            entry, exit_ = EntryIntent.WATCH, ExitIntent.EXIT
        else:
            entry, exit_ = EntryIntent.WATCH, ExitIntent.HOLD
        return self._verdict(
            bundle, entry, exit_, DataStatus.COMPLETE, dated_events, state, opportunity
        )

    def _verdict(self, bundle, entry, exit_, status, events=None, state=None, opportunity=None):
        return StrategyVerdict(
            verdict_schema_version="1",
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            ticker=bundle.ticker,
            as_of=bundle.as_of,
            entry=EntryVerdict(
                intent=entry, opportunity=opportunity, data_status=status, reasons=[]
            ),
            exit=ExitVerdict(intent=exit_, data_status=status, reasons=[]),
            events=events or [],
            strategy_state=state,
        )
