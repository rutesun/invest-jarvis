"""Replay SWING_W150 chart observations and completed signals from a price prefix."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from src.strategies.models import (
    BarFinality,
    ObservationCode,
    ObservationStatus,
    SignalFinality,
    StrategyObservationEpisode,
    StrategySignal,
    SupportAnchor,
    SupportTestState,
    UpCycleState,
)
from src.strategies.observations import make_observation
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.strategies.swing_w150.parameters import (
    SWING_W150_PARAMETER_REGISTRY,
    V2_INACTIVE_REASON,
    SwingW150Parameters,
    validate_pullback_policy,
)
from src.strategies.swing_w150.support_ladder import (
    advance_support_tests,
    anchor_value,
    select_support,
)
from src.strategies.swing_w150.up_cycle import advance_up_cycle
from src.tools.technical.chart_analysis.models import ChartAnalysis, FactSelection
from src.tools.technical.scorecard_models import DataStatus, Direction, Evidence, Importance


STRATEGY_ID = "SWING_W150"
STRATEGY_VERSION = "SWING_W150_V2"
_PRIORITY = {
    "SMA150_EXIT": 0,
    "OVERHEAT_CORRECTION": 1,
    "POST_OVERHEAT_RECOVERY_ENTRY": 2,
    "PULLBACK_REVERSAL_ENTRY": 3,
    "TREND_BREAKOUT_ENTRY": 4,
    "DEEP_RECOVERY_ENTRY": 5,
    "OVERHEAT": 6,
    "OVERHEAT_RESOLVED": 6,
    "OVERHEAT_EXPIRED": 6,
}


class SwingSignalDetection(BaseModel):
    common_analyses: tuple[ChartAnalysis, ...] = Field(default=(), exclude=True)
    fact_selections: tuple[FactSelection, ...] = Field(default=(), exclude=True)
    strategy_id: str
    strategy_version: str
    parameter_set_version: str
    parameter_fingerprint: str
    ticker: str
    as_of: date
    observation_history: list[StrategyObservationEpisode]
    signal_history: list[StrategySignal]
    current_signals: list[StrategySignal]
    data_status: DataStatus
    up_cycle: UpCycleState | None = None
    support_tests: list[SupportTestState] | None = None
    pullback_policy_inactive_reason: str | None = None

    @model_validator(mode="after")
    def check_current_signals(self) -> SwingSignalDetection:
        if self.current_signals != [
            signal for signal in self.signal_history if signal.occurred_on == self.as_of
        ]:
            raise ValueError("current_signals must equal signals from as_of")
        return self


class _OverheatPhase(StrEnum):
    NORMAL = "normal"
    OVERHEATED = "overheated"
    CORRECTED = "corrected"


class _PullbackPhase(StrEnum):
    NONE = "none"
    WATCHING = "watching"


class _Sma150Phase(StrEnum):
    ABOVE = "above"
    BELOW_ONCE = "below_once"
    LATCHED_EXIT = "latched_exit"


def _number(row: pd.Series, column: str) -> float | None:
    value = row.get(column)
    return float(value) if value is not None and pd.notna(value) else None


def _evidence(code: str, observed: float | None, reference: float | None = None) -> Evidence:
    return Evidence(
        code=code,
        message=code.replace("_", " ").lower(),
        observed_value=observed,
        reference_value=reference,
        importance=Importance.HIGH,
        source="SWING_W150_V2",
    )


def _direction_evidence(code: str, delta: float | None) -> Evidence:
    direction = (
        "UNKNOWN"
        if delta is None
        else "RISING"
        if delta > 0
        else "FALLING"
        if delta < 0
        else "FLAT"
    )
    return _evidence(f"{code}_DIRECTION_{direction}", delta, 0.0)


def _delta(row: pd.Series, previous: pd.Series | None, column: str) -> float | None:
    current = _number(row, column)
    prior = _number(previous, column) if previous is not None else None
    return current - prior if current is not None and prior is not None else None


def _session(index_value: object) -> date:
    if isinstance(index_value, pd.Timestamp):
        return index_value.date()
    if isinstance(index_value, date):
        return index_value
    raise ValueError("SwingFeatureFrame index must contain dates")


def _support_candidates(row: pd.Series, params: SwingW150Parameters) -> tuple[str, ...]:
    close, low, atr = (_number(row, key) for key in ("Close", "Low", "ATR"))
    sma50, sma150, sma200 = (_number(row, f"SMA_{p}") for p in (50, 150, 200))
    slopes = [
        _number(row, f"SMA_{p}_Slope_{params.direction_lookback_bars}") for p in (50, 150, 200)
    ]
    if (
        any(value is None for value in (close, low, atr, sma50, sma150, sma200))
        or any(value is None or value <= 0 for value in slopes)
        or not sma50 > sma150 > sma200
        or _number(row, "SuperTrend_Dir") != 1
        or atr <= 0
    ):
        return ()
    distance = params.pullback_support_atr_distance * atr
    supports = [
        *(f"SMA_{period}" for period in params.pullback_support_sma_periods),
        "SuperTrend_Up",
    ]
    return tuple(
        support
        for support in supports
        if (level := _number(row, support)) is not None
        and low <= level + distance
        and close >= level
        and low >= level - distance
    )


def _pullback_evidence(
    row: pd.Series,
    previous: pd.Series | None,
    supports: tuple[str, ...],
    params: SwingW150Parameters,
) -> list[Evidence]:
    close = _number(row, "Close")
    evidence = [_evidence(support, close, _number(row, support)) for support in supports]
    for period in (50, 150, 200):
        evidence.append(
            _direction_evidence(
                f"SMA_{period}_SLOPE",
                _number(row, f"SMA_{period}_Slope_{params.direction_lookback_bars}"),
            )
        )
    for indicator, reference in (("cRSI", 50.0), ("MACD", 0.0)):
        value = _number(row, indicator)
        if value is not None:
            evidence.append(_evidence(indicator, value, reference))
        evidence.append(_direction_evidence(indicator, _delta(row, previous, indicator)))
    return evidence


def _trend_evidence(row: pd.Series, params: SwingW150Parameters) -> list[Evidence]:
    volume = _number(row, "Volume")
    average = _number(row, "Vol_SMA_20")
    return [
        _evidence(
            "TREND_BREAKOUT_PRICE",
            _number(row, "Close"),
            _number(row, "Trend_Breakout_High_Prev"),
        ),
        _evidence(
            "VOLUME_MULTIPLE",
            volume / average
            if volume is not None and average is not None and average > 0
            else None,
            params.trend_breakout_volume_multiple,
        ),
        _direction_evidence(
            "SMA_150_SLOPE",
            _number(row, f"SMA_150_Slope_{params.direction_lookback_bars}"),
        ),
    ]


def _deep_evidence(row: pd.Series, previous: pd.Series) -> list[Evidence]:
    close = _number(row, "Close")
    sma50 = _number(row, "SMA_50")
    high = _number(row, "Deep_Recovery_High_Prev")
    prior_close = _number(previous, "Close")
    prior_high = _number(previous, "Deep_Recovery_High_Prev")
    prior_sma50 = _number(previous, "SMA_50")
    evidence = [
        _evidence("SMA_20_RECOVERY", close, _number(row, "SMA_20")),
        _evidence("SMA_50_RECOVERY", close, sma50),
        _evidence("HIGHER_LOW", float(bool(row["Higher_Low"])), 1.0),
        _direction_evidence("SUPERTREND", _number(row, "SuperTrend_Dir")),
    ]
    if (
        close is not None
        and high is not None
        and prior_close is not None
        and prior_high is not None
        and close > high
        and prior_close <= prior_high
    ):
        evidence.append(_evidence("DEEP_BREAKOUT_PRICE", close, high))
    if (
        close is not None
        and sma50 is not None
        and prior_close is not None
        and prior_sma50 is not None
        and prior_close <= prior_sma50
        and close > sma50
    ):
        evidence.append(_evidence("DEEP_RECLAIM_SMA50", close, sma50))
    return evidence


_LADDER_COLUMNS = {"SUPERTREND": "SuperTrend_Up", "SMA50": "SMA_50", "SMA150": "SMA_150"}


def _cycle_anchors(row, *, cycle, day, entries):
    anchors = []
    for kind, column in _LADDER_COLUMNS.items():
        level = _number(row, column)
        if (
            level is None
            or level <= 0
            or (kind == "SUPERTREND" and _number(row, "SuperTrend_Dir") != 1)
        ):
            continue
        anchors.append(
            SupportAnchor(
                anchor_id=f"{cycle.cycle_id}:{kind}",
                anchor_type=kind,
                is_dynamic=True,
                origin_on=day,
                origin_price=Decimal(str(level)),
                current_value=Decimal(str(level)),
                cycle_id=cycle.cycle_id,
            )
        )
    breakout_sources = []
    if bool(row.get("Price_Breakout_Event", False)):
        breakout_sources.append((None, _number(row, "Trend_Breakout_High_Prev")))
    for signal in entries:
        code = (
            "TREND_BREAKOUT_PRICE"
            if signal.code == "TREND_BREAKOUT_ENTRY"
            else "DEEP_BREAKOUT_PRICE"
        )
        level = next((item.reference_value for item in signal.evidence if item.code == code), None)
        if level is not None:
            breakout_sources.append((signal.signal_id, level))
    for source, level in breakout_sources:
        if level is None or level <= 0:
            continue
        anchors.append(
            SupportAnchor(
                anchor_id=f"{cycle.cycle_id}:BREAKOUT:{day}:{source or 'PRICE'}:{level}",
                anchor_type="PRIOR_BREAKOUT_LEVEL",
                is_dynamic=False,
                origin_on=day,
                origin_price=Decimal(str(level)),
                current_value=Decimal(str(level)),
                source_signal_id=source,
                cycle_id=cycle.cycle_id,
            )
        )
    return anchors


@dataclass
class _LadderWatch:
    episode: StrategyObservationEpisode
    test_started_on: date
    bar: int


def _ladder_watch(
    watch,
    selected,
    *,
    ticker,
    row,
    previous,
    completed_highs,
    bar,
    day,
    finality,
    cycle,
    exited,
    params,
    observation_params,
    observations,
    emit,
):
    close, low, atr = (_number(row, column) for column in ("Close", "Low", "ATR"))
    level = float(selected.anchor.current_value) if selected is not None else None
    same_test = bool(
        watch is not None
        and selected is not None
        and watch.episode.anchor_id == selected.anchor.anchor_id
        and watch.test_started_on == selected.started_on
    )
    allowed = cycle.status == "ACTIVE" and not exited
    can_open = bool(
        allowed
        and selected is not None
        and atr is not None
        and atr > 0
        and low is not None
        and close is not None
        and close >= level
        and abs(low - level) <= params.pullback_support_atr_distance * atr
        and selected.reclaimed_on != day
    )
    completed = False
    switched = False
    if watch is not None:
        episode = watch.episode
        episode.finality = SignalFinality(finality.value)
        episode.status_as_of = day
        if not allowed or not same_test:
            episode.status = ObservationStatus.INVALIDATED
            switched = True
        elif bar - watch.bar >= params.pullback_watch_expiry_bars:
            episode.status = ObservationStatus.EXPIRED
        else:
            column = _LADDER_COLUMNS.get(selected.anchor.anchor_type, "PRIOR_BREAKOUT_LEVEL")
            details = _pullback_evidence(row, previous, (), params)
            episode.evidence = [_evidence(column, close, level), *details]
            prior = completed_highs[-params.pullback_reversal_high_lookback :]
            prior_high = max((high for high in prior if high is not None), default=None)
            reversal = bool(
                bar > watch.bar
                and selected.reclaimed_on != day
                and prior_high is not None
                and close is not None
                and close > level
                and close > prior_high
            )
            if reversal:
                emit("PULLBACK_REVERSAL_ENTRY", level, episode.evidence)
                episode.status = ObservationStatus.RESOLVED_TO_SIGNAL
        if episode.status is not ObservationStatus.ACTIVE:
            episode.ended_on = day
            completed = True
            watch = None
    if watch is None and can_open and (not completed or switched):
        anchor = selected.anchor
        column = _LADDER_COLUMNS.get(anchor.anchor_type, "PRIOR_BREAKOUT_LEVEL")
        episode = make_observation(
            ticker=ticker,
            code=ObservationCode.PULLBACK_WATCH,
            origin=day,
            params=observation_params,
            finality=SignalFinality(finality.value),
            evidence=[
                _evidence(column, close, level),
                *_pullback_evidence(row, previous, (), params),
            ],
            anchor_id=anchor.anchor_id,
            anchor_type=anchor.anchor_type,
            anchor_origin_on=day,
            anchor_origin_price=anchor.current_value,
            cycle_id=cycle.cycle_id,
        )
        observations.append(episode)
        watch = _LadderWatch(episode, selected.started_on, bar)
    return watch


def iter_swing_detection(
    ticker: str,
    features: SwingFeatureFrame,
    params: SwingW150Parameters,
    *,
    common_analysis: ChartAnalysis | None = None,
) -> Iterator[SwingSignalDetection]:
    """Yield snapshots with public facts bound to each observed input prefix."""
    yield from _iter_swing_detection(
        ticker, features, params, common_analysis=common_analysis, metadata_mode="all"
    )


def _iter_swing_detection(
    ticker: str,
    features: SwingFeatureFrame,
    params: SwingW150Parameters,
    *,
    common_analysis: ChartAnalysis | None = None,
    metadata_mode: str,
) -> Iterator[SwingSignalDetection]:
    """Shared numerical replay; internal callers may omit unused public facts."""
    SWING_W150_PARAMETER_REGISTRY.validate(params)
    ladder_enabled = validate_pullback_policy(params)
    frame = features.frame
    if len(features.finalities) != len(frame):
        raise ValueError("feature finalities length must match bars")
    if common_analysis is None and features.data_status is DataStatus.COMPLETE:
        from src.strategies.swing_w150.common import swing_analysis

        common_analysis = swing_analysis(ticker, features, params)
    common_values = None
    common_items = ()
    common_selections = ()
    if common_analysis is not None:
        from src.strategies.swing_w150.common import (
            feature_scope,
            requested_items,
            selections,
            swing_analysis,
            swing_rules,
            validate_analysis,
        )

        validate_analysis(common_analysis, feature_scope(ticker, features), swing_rules(params))
        common_items = requested_items(common_analysis, swing_rules(params))
        common_values = dict(
            next(
                item.evidence
                for item in common_items
                if item.rule_id == "chart.deep_recovery.swing"
            )
        )
        common_values["trend_breakout"] = next(
            item.evidence["trigger"]
            for item in common_items
            if item.rule_id == "chart.close_breakout.strict"
        )
        common_selections = selections(
            common_analysis,
            tuple(
                rule
                for rule in swing_rules(params)
                if rule.rule_id != "chart.structure_breakdown.swing"
                and (ladder_enabled or rule.rule_id != "chart.pivot.span3")
            ),
        )
    fingerprint = params.parameter_fingerprint
    observation_params = ObservationParameters()
    up_cycle = UpCycleState(finality=BarFinality.FINAL) if ladder_enabled else None
    support_tests: list[SupportTestState] = []
    ladder_watch = None
    completed_highs: list[float | None] = []
    pivot_events = (
        tuple(
            __import__("types").SimpleNamespace(**dict(item.evidence))
            for item in common_items
            if item.rule_id == "chart.pivot.span3"
        )
        if common_analysis is not None
        and ladder_enabled
        and features.data_status is DataStatus.COMPLETE
        else ()
    )
    deep_rows = (
        common_values["deep_recovery"]
        if common_values is not None
        else np.zeros(len(frame), dtype=bool)
    )
    observations: list[StrategyObservationEpisode] = []
    signals: list[StrategySignal] = []
    overheat_phase = _OverheatPhase.NORMAL
    overheat_last_bar = -1
    corrected_bar = -1
    corrected_episode: StrategyObservationEpisode | None = None
    pullback_phase = _PullbackPhase.NONE
    pullback_bar = -1
    pullback_supports: tuple[str, ...] = ()
    pullback_episode: StrategyObservationEpisode | None = None
    sma150_phase = _Sma150Phase.ABOVE
    below_sma150_count = 0
    sma150_armed = False

    for bar, (stamp, row) in enumerate(frame.iterrows()):
        if ladder_enabled and bar and features.finalities[bar - 1] is BarFinality.FINAL:
            completed_highs.append(_number(frame.iloc[bar - 1], "High"))
        committed = None
        if ladder_enabled and features.finalities[bar] is BarFinality.PROVISIONAL:
            # Preview branches may emit PROVISIONAL results, never seed later FINAL state.
            committed = deepcopy(
                (
                    observations,
                    signals,
                    overheat_phase,
                    overheat_last_bar,
                    corrected_bar,
                    corrected_episode,
                    sma150_phase,
                    below_sma150_count,
                    sma150_armed,
                    ladder_watch,
                )
            )
        day = _session(stamp)
        for episode in (corrected_episode, pullback_episode):
            if episode is not None:
                episode.finality = SignalFinality(features.finalities[bar].value)
        previous = frame.iloc[bar - 1] if bar else None
        close = _number(row, "Close")
        sma150 = _number(row, "SMA_150")
        sma20 = _number(row, "SMA_20")
        sma50 = _number(row, "SMA_50")
        today: list[StrategySignal] = []

        def emit(
            code: str,
            reference: float | None = None,
            details: list[Evidence] | None = None,
            *,
            close: float | None = close,
            day: date = day,
            finality: BarFinality = features.finalities[bar],
            today: list[StrategySignal] = today,
        ) -> None:
            assert close is not None
            direction = (
                Direction.FALLING
                if code in {"SMA150_EXIT", "OVERHEAT_CORRECTION"}
                else Direction.RISING
                if code.endswith("ENTRY") or code == "OVERHEAT"
                else None
            )
            today.append(
                StrategySignal(
                    signal_id=f"{STRATEGY_VERSION}:{ticker}:{day.isoformat()}:{code}:{fingerprint}",
                    strategy_id=STRATEGY_ID,
                    strategy_version=STRATEGY_VERSION,
                    parameter_set_version=params.parameter_set_version,
                    parameter_fingerprint=fingerprint,
                    code=code,
                    occurred_on=day,
                    finality=(
                        SignalFinality.FINAL
                        if finality is BarFinality.FINAL
                        else SignalFinality.PROVISIONAL
                    ),
                    direction=direction,
                    signal_price=Decimal(str(close)),
                    evidence=[_evidence(code, close, reference), *(details or [])],
                    data_status=features.data_status,
                )
            )

        if (
            features.data_status is DataStatus.COMPLETE
            and bar + 1 >= params.minimum_history_bars
            and close is not None
        ):
            exited = False
            if sma150 is not None:
                if close > sma150:
                    slope150 = _number(row, f"SMA_150_Slope_{params.direction_lookback_bars}")
                    if sma150_phase is _Sma150Phase.LATCHED_EXIT:
                        sma150_armed = bool(slope150 is not None and slope150 > 0)
                    elif slope150 is not None and slope150 > 0:
                        sma150_armed = True
                    sma150_phase = _Sma150Phase.ABOVE
                    below_sma150_count = 0
                elif close < sma150:
                    if sma150_armed and sma150_phase is not _Sma150Phase.LATCHED_EXIT:
                        below_sma150_count += 1
                    if (
                        sma150_armed
                        and sma150_phase is not _Sma150Phase.LATCHED_EXIT
                        and below_sma150_count >= params.sma_exit_consecutive_closes
                    ):
                        emit(
                            "SMA150_EXIT",
                            sma150,
                            [
                                _evidence("CLOSE_VS_SMA150", close, sma150),
                                _evidence(
                                    "CONSECUTIVE_BELOW_SMA150",
                                    float(below_sma150_count),
                                    float(params.sma_exit_consecutive_closes),
                                ),
                            ],
                        )
                        sma150_phase = _Sma150Phase.LATCHED_EXIT
                        sma150_armed = False
                        exited = True
                    elif sma150_armed and sma150_phase is _Sma150Phase.ABOVE:
                        sma150_phase = _Sma150Phase.BELOW_ONCE
                else:
                    below_sma150_count = 0

            if previous is not None and common_values["trend_breakout"][bar]:
                emit(
                    "TREND_BREAKOUT_ENTRY",
                    _number(row, "Trend_Breakout_High_Prev"),
                    _trend_evidence(row, params),
                )
            if previous is not None and (
                bool(deep_rows[bar]) and common_values["deep_recovery_trigger"][bar]
            ):
                emit(
                    "DEEP_RECOVERY_ENTRY",
                    _number(row, "Deep_Recovery_High_Prev"),
                    _deep_evidence(row, previous),
                )

            if ladder_enabled:
                finality = features.finalities[bar]
                entries = [
                    item
                    for item in today
                    if item.code in {"TREND_BREAKOUT_ENTRY", "DEEP_RECOVERY_ENTRY"}
                ]
                up_cycle = advance_up_cycle(
                    up_cycle,
                    row,
                    ticker=ticker,
                    day=day,
                    finality=finality,
                    confirmed_pivots=[
                        event for event in pivot_events if event.confirmed_index == bar
                    ],
                    independent_entries=entries,
                    sma150_failed=False,
                    params=params,
                )
                if up_cycle.status == "ACTIVE":
                    older = [
                        state
                        for state in support_tests
                        if state.anchor.cycle_id != up_cycle.cycle_id
                    ]
                    current = advance_support_tests(
                        [
                            state
                            for state in support_tests
                            if state.anchor.cycle_id == up_cycle.cycle_id
                        ],
                        row,
                        new_anchors=_cycle_anchors(row, cycle=up_cycle, day=day, entries=entries),
                        day=day,
                        finality=finality,
                        params=params.support_cycle,
                    )
                    support_tests = [*older, *current]
                    up_cycle = advance_up_cycle(
                        up_cycle,
                        row,
                        ticker=ticker,
                        day=day,
                        finality=finality,
                        confirmed_pivots=(),
                        independent_entries=(),
                        sma150_failed=any(
                            state.anchor.anchor_type == "SMA150" and state.status == "FAILED"
                            for state in current
                        ),
                        params=params,
                    )

                current_tests = [
                    state for state in support_tests if state.anchor.cycle_id == up_cycle.cycle_id
                ]
                if finality is BarFinality.PROVISIONAL:
                    # Use today's dynamic line for preview eligibility without committing tests.
                    current_tests = [
                        state.model_copy(
                            update={
                                "anchor": state.anchor.model_copy(
                                    update={"current_value": anchor_value(state.anchor, row)}
                                )
                            }
                        )
                        for state in current_tests
                    ]
                selected = select_support(
                    current_tests,
                    close=close,
                    low=_number(row, "Low"),
                    atr=_number(row, "ATR"),
                    params=params,
                )
                ladder_watch = _ladder_watch(
                    ladder_watch,
                    selected,
                    ticker=ticker,
                    row=row,
                    previous=previous,
                    completed_highs=completed_highs,
                    bar=bar,
                    day=day,
                    finality=finality,
                    cycle=up_cycle,
                    exited=exited,
                    params=params,
                    observation_params=observation_params,
                    observations=observations,
                    emit=emit,
                )
                if ladder_watch is None:
                    for episode in reversed(observations):
                        if episode.code == "PULLBACK_WATCH" and episode.ended_on == day:
                            if episode.status == ObservationStatus.RESOLVED_TO_SIGNAL:
                                episode.source_signal_id = today[-1].signal_id
                            break

            if sma50 is not None and sma50 > 0 and sma20 is not None and previous is not None:
                extension = close / sma50 - 1
                previous_close = _number(previous, "Close")
                previous_sma20 = _number(previous, "SMA_20")
                correction = bool(
                    previous_close is not None
                    and previous_sma20 is not None
                    and close < sma20
                    and previous_close >= previous_sma20
                )
                recovery = bool(
                    previous is not None
                    and close > sma20
                    and (prior_high := _number(previous, "High")) is not None
                    and close > prior_high
                )
                if exited:
                    if overheat_phase is _OverheatPhase.OVERHEATED and correction:
                        emit(
                            "OVERHEAT_CORRECTION",
                            sma20,
                            [
                                _evidence("SMA20_CROSS_DOWN", close, sma20),
                                _evidence("PRIOR_CLOSE_VS_SMA20", previous_close, previous_sma20),
                            ],
                        )
                    if corrected_episode is not None:
                        corrected_episode.status = ObservationStatus.INVALIDATED
                        corrected_episode.status_as_of = day
                        corrected_episode.ended_on = day
                        corrected_episode = None
                    overheat_phase = _OverheatPhase.NORMAL
                elif overheat_phase is _OverheatPhase.NORMAL:
                    if extension >= params.overheat_extension:
                        emit(
                            "OVERHEAT",
                            sma50,
                            [_evidence("OVERHEAT_EXTENSION", extension, params.overheat_extension)],
                        )
                        overheat_phase = _OverheatPhase.OVERHEATED
                        overheat_last_bar = bar
                elif overheat_phase is _OverheatPhase.OVERHEATED:
                    if extension >= params.overheat_extension:
                        overheat_last_bar = bar
                    if correction:
                        emit(
                            "OVERHEAT_CORRECTION",
                            sma20,
                            [
                                _evidence("SMA20_CROSS_DOWN", close, sma20),
                                _evidence("PRIOR_CLOSE_VS_SMA20", previous_close, previous_sma20),
                            ],
                        )
                        overheat_phase = _OverheatPhase.CORRECTED
                        corrected_bar = bar
                        corrected_episode = make_observation(
                            ticker=ticker,
                            code=ObservationCode.POST_OVERHEAT_RECOVERY_WATCH,
                            origin=day,
                            params=observation_params,
                            finality=SignalFinality(features.finalities[bar].value),
                            status_as_of=day,
                            ended_on=None,
                            status=ObservationStatus.ACTIVE,
                            evidence=[_evidence("SMA_20", close, sma20)],
                        )
                        observations.append(corrected_episode)
                    elif extension <= params.overheat_reset_extension:
                        emit(
                            "OVERHEAT_RESOLVED",
                            sma50,
                            [
                                _evidence(
                                    "OVERHEAT_EXTENSION",
                                    extension,
                                    params.overheat_reset_extension,
                                )
                            ],
                        )
                        overheat_phase = _OverheatPhase.NORMAL
                    elif bar - overheat_last_bar >= params.overheat_expiry_bars:
                        emit(
                            "OVERHEAT_EXPIRED",
                            sma50,
                            [
                                _evidence(
                                    "OVERHEAT_EXTENSION",
                                    extension,
                                    params.overheat_extension,
                                ),
                                _evidence(
                                    "OVERHEAT_AGE_BARS",
                                    float(bar - overheat_last_bar),
                                    float(params.overheat_expiry_bars),
                                ),
                            ],
                        )
                        overheat_phase = _OverheatPhase.NORMAL
                elif overheat_phase is _OverheatPhase.CORRECTED:
                    assert corrected_episode is not None
                    if recovery:
                        emit(
                            "POST_OVERHEAT_RECOVERY_ENTRY",
                            sma20,
                            [
                                _evidence("SMA20_RECOVERY", close, sma20),
                                _evidence("PRIOR_HIGH_BREAK", close, prior_high),
                                _evidence(
                                    "CORRECTED_AGE_BARS",
                                    float(bar - corrected_bar),
                                    float(params.post_correction_recovery_expiry_bars),
                                ),
                            ],
                        )
                        corrected_episode.status = ObservationStatus.RESOLVED_TO_SIGNAL
                        corrected_episode.ended_on = day
                        corrected_episode.status_as_of = day
                        corrected_episode = None
                        overheat_phase = _OverheatPhase.NORMAL
                    elif bar - corrected_bar >= params.post_correction_recovery_expiry_bars:
                        corrected_episode.status = ObservationStatus.EXPIRED
                        corrected_episode.ended_on = day
                        corrected_episode.status_as_of = day
                        corrected_episode = None
                        overheat_phase = _OverheatPhase.NORMAL

            supports = _support_candidates(row, params) if not ladder_enabled else ()
            completed_watch = False
            restart_watch = False
            if pullback_phase is _PullbackPhase.WATCHING:
                assert pullback_episode is not None
                levels = [_number(row, support) for support in pullback_supports]
                max_support = max((level for level in levels if level is not None), default=None)
                if max_support is None:
                    # SuperTrend_Up disappears when a Supertrend-only watch turns bearish.
                    pullback_episode.evidence = _pullback_evidence(
                        row, previous, pullback_supports, params
                    )
                atr = _number(row, "ATR")
                previous_high = (
                    float(
                        frame["High"].iloc[bar - params.pullback_reversal_high_lookback : bar].max()
                    )
                    if bar >= params.pullback_reversal_high_lookback
                    else None
                )
                reversal = bool(
                    max_support is not None
                    and previous_high is not None
                    and close > max_support
                    and close > previous_high
                )
                invalidated = bool(
                    max_support is None
                    or (
                        atr is not None
                        and close < max_support - params.pullback_support_atr_distance * atr
                    )
                )
                if reversal:
                    emit("PULLBACK_REVERSAL_ENTRY", max_support)
                    today[-1].evidence.extend(
                        _pullback_evidence(row, previous, pullback_supports, params)
                    )
                    pullback_episode.status = ObservationStatus.RESOLVED_TO_SIGNAL
                elif exited or invalidated:
                    pullback_episode.status = ObservationStatus.INVALIDATED
                elif bar - pullback_bar >= params.pullback_watch_expiry_bars:
                    pullback_episode.status = ObservationStatus.EXPIRED
                elif supports and (
                    supports != pullback_supports
                    or (previous is not None and not _support_candidates(previous, params))
                ):
                    pullback_episode.status = ObservationStatus.EXPIRED
                    restart_watch = True
                if pullback_episode.status is not ObservationStatus.ACTIVE:
                    completed_watch = True
                    if exited:
                        pullback_episode.status = ObservationStatus.INVALIDATED
                    pullback_episode.ended_on = day
                    pullback_episode.status_as_of = day
                    pullback_episode = None
                    pullback_phase = _PullbackPhase.NONE
                else:
                    pullback_episode.status_as_of = day
                    pullback_episode.evidence = _pullback_evidence(
                        row, previous, pullback_supports, params
                    )
            if (
                pullback_phase is _PullbackPhase.NONE
                and supports
                and not exited
                and (not completed_watch or restart_watch)
            ):
                pullback_phase = _PullbackPhase.WATCHING
                pullback_bar = bar
                pullback_supports = supports
                pullback_episode = make_observation(
                    ticker=ticker,
                    code=ObservationCode.PULLBACK_WATCH,
                    origin=day,
                    params=observation_params,
                    finality=SignalFinality(features.finalities[bar].value),
                    status_as_of=day,
                    ended_on=None,
                    status=ObservationStatus.ACTIVE,
                    evidence=_pullback_evidence(row, previous, supports, params),
                )
                observations.append(pullback_episode)

        if corrected_episode is not None:
            corrected_episode.status_as_of = day
        today.sort(key=lambda signal: _PRIORITY[signal.code])
        signals.extend(today)
        snapshot_analysis = None
        snapshot_selections = ()
        if common_analysis is not None and (
            metadata_mode == "all" or (metadata_mode == "latest" and bar == len(frame) - 1)
        ):
            if bar == len(frame) - 1:
                snapshot_analysis = common_analysis
                snapshot_selections = common_selections
            else:
                prefix = replace(
                    features,
                    frame=frame.iloc[: bar + 1],
                    finalities=features.finalities[: bar + 1],
                )
                snapshot_analysis = swing_analysis(ticker, prefix, params)
                snapshot_selections = selections(
                    snapshot_analysis,
                    tuple(
                        rule
                        for rule in swing_rules(params)
                        if rule.rule_id != "chart.structure_breakdown.swing"
                        and (ladder_enabled or rule.rule_id != "chart.pivot.span3")
                    ),
                )
        yield SwingSignalDetection(
            common_analyses=(snapshot_analysis,) if snapshot_analysis is not None else (),
            fact_selections=snapshot_selections,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            parameter_set_version=params.parameter_set_version,
            parameter_fingerprint=fingerprint,
            ticker=ticker,
            as_of=day,
            observation_history=[episode.model_copy(deep=True) for episode in observations],
            signal_history=list(signals),
            current_signals=today,
            data_status=(
                features.data_status
                if bar + 1 >= params.minimum_history_bars
                else DataStatus.INSUFFICIENT_DATA
            ),
            up_cycle=up_cycle,
            support_tests=list(support_tests) if ladder_enabled else None,
            pullback_policy_inactive_reason=(
                "NOT_EVALUATED: incomplete feature coverage or insufficient history"
                if ladder_enabled
                and (
                    features.data_status is not DataStatus.COMPLETE
                    or bar + 1 < params.minimum_history_bars
                )
                else None
                if ladder_enabled
                else V2_INACTIVE_REASON
            ),
        )
        if committed is not None:
            (
                observations,
                signals,
                overheat_phase,
                overheat_last_bar,
                corrected_bar,
                corrected_episode,
                sma150_phase,
                below_sma150_count,
                sma150_armed,
                ladder_watch,
            ) = committed


def detect_swing(
    ticker: str,
    features: SwingFeatureFrame,
    params: SwingW150Parameters,
    *,
    common_analysis: ChartAnalysis | None = None,
) -> SwingSignalDetection:
    """Return the latest replay snapshot; no storage, clock, or position input is used."""
    result: SwingSignalDetection | None = None
    for snapshot in _iter_swing_detection(
        ticker, features, params, common_analysis=common_analysis, metadata_mode="latest"
    ):
        result = snapshot
    if result is None:
        raise ValueError("SwingFeatureFrame must contain at least one bar")
    return result
