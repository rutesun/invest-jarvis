"""Causal Observation replay. Future labels and portfolio state stay outside Strategy."""

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal

import pandas as pd

from src.strategies.models import (
    BarFinality,
    ObservationCode,
    ObservationSourceContext,
    ObservationStatus,
    SignalFinality,
    StrategyObservationEpisode,
    StrategySignal,
)
from src.strategies.observations import make_observation
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.strategies.swing_w150.support_ladder import number
from src.tools.technical.pivots import confirmed_pivot_events
from src.tools.technical.scorecard_models import Evidence, Importance


def _truth(row, column):
    value = row.get(column)
    return value is not None and pd.notna(value) and bool(value)


def evaluate_observations(
    ticker: str,
    features: SwingFeatureFrame,
    signals: Sequence[StrategySignal],
    setups: Sequence[StrategyObservationEpisode],
    *,
    source_contexts: Sequence[ObservationSourceContext],
    params: ObservationParameters,
) -> list[StrategyObservationEpisode]:
    """One record per confirmed event/episode; unfinished bars do not commit history."""
    frame = features.frame
    if len(frame) and features.finalities[-1] == BarFinality.PROVISIONAL:
        final_features = replace(
            features, frame=frame.iloc[:-1], finalities=features.finalities[:-1]
        )
        final_history = evaluate_observations(
            ticker, final_features, signals, setups, source_contexts=source_contexts, params=params
        )
        preview_features = replace(
            features, finalities=(*features.finalities[:-1], BarFinality.FINAL)
        )
        preview_contexts = [
            context.model_copy(
                update={
                    "signal": context.signal.model_copy(update={"finality": SignalFinality.FINAL})
                }
            )
            if context.signal.finality is SignalFinality.PROVISIONAL
            and context.signal.occurred_on == frame.index[-1].date()
            else context
            for context in source_contexts
        ]
        preview = evaluate_observations(
            ticker,
            preview_features,
            signals,
            setups,
            source_contexts=preview_contexts,
            params=params,
        )
        known = {episode.observation_id for episode in final_history}
        additions = [
            episode.model_copy(update={"finality": SignalFinality.PROVISIONAL})
            for episode in preview
            if episode.observation_id not in known and episode.started_on == frame.index[-1].date()
        ]
        return sorted(
            final_history + additions,
            key=lambda item: (item.started_on, item.code, item.observation_id),
        )
    history = list(setups)
    active = {}
    breached = {}
    origins = {}
    pivots = {}
    if {"High", "Low"} <= set(frame.columns):
        for pivot in confirmed_pivot_events(
            frame["High"].to_numpy(float),
            frame["Low"].to_numpy(float),
            final_mask=[finality == BarFinality.FINAL for finality in features.finalities],
        ):
            if pivot.relation is not None:
                pivots.setdefault(pivot.confirmed_index, []).append(pivot)

    def evidence(code, value, reference):
        return Evidence(
            code=code,
            message=code.replace("_", " ").lower(),
            observed_value=value,
            reference_value=reference,
            importance=Importance.HIGH,
            source="OBSERVATION_V1",
        )

    def make(code, day, *, event=False, evidence_value=None, reference=None, details=(), **context):
        return make_observation(
            ticker=ticker,
            code=ObservationCode(code),
            origin=day,
            params=params,
            evidence=[evidence(code, evidence_value, reference), *details],
            **(
                {"status": ObservationStatus.RESOLVED, "ended_on": day, "confirmed_on": day}
                if event
                else {}
            ),
            **context,
        )

    def episode(key, code, condition, day, *, evidence_value, reference, details=(), **context):
        def update_evidence(item):
            # 최초 실측은 보존하고 마지막으로 관측한 실측을 별도 typed evidence로 갱신한다.
            origin = [value for value in item.evidence if not value.code.endswith("_CURRENT")]
            current = [evidence(f"{code}_CURRENT", evidence_value, reference)]
            current.extend(
                value.model_copy(update={"code": f"{value.code}_CURRENT"}) for value in details
            )
            return origin + current

        if condition:
            if key not in active:
                item = make(
                    code,
                    day,
                    evidence_value=evidence_value,
                    reference=reference,
                    details=details,
                    **context,
                )
                active[key] = len(history)
                history.append(item)
            else:
                index = active[key]
                history[index] = history[index].model_copy(
                    update={
                        "status_as_of": day,
                        "evidence": update_evidence(history[index]),
                        **context,
                    }
                )
        elif key in active:
            index = active.pop(key)
            history[index] = history[index].model_copy(
                update={
                    "status": ObservationStatus.RESOLVED,
                    "status_as_of": day,
                    "ended_on": day,
                    "evidence": update_evidence(history[index]),
                    **context,
                }
            )

    for index, (stamp, row) in enumerate(frame.iterrows()):
        if features.finalities[index] != BarFinality.FINAL:
            continue
        day = stamp.date()
        close, previous, ratio = (
            number(row, key) for key in ("Close", "Previous_Close", "Volume_Ratio_Prev20")
        )
        for pivot in pivots.get(index, []):
            history.append(
                make(
                    pivot.relation,
                    day,
                    event=True,
                    evidence_value=pivot.price,
                    reference=pivot.previous_pivot_price,
                    pivot_date=frame.index[pivot.pivot_index].date(),
                )
            )
        if close is not None and previous is not None and ratio is not None:
            for code, threshold, direction in [
                ("UP_VOLUME_EXPANSION", params.up_volume_ratio, close > previous),
                ("DOWN_VOLUME_EXPANSION", params.down_volume_ratio, close < previous),
            ]:
                if threshold is not None and direction and ratio >= threshold:
                    history.append(
                        make(
                            code,
                            day,
                            event=True,
                            evidence_value=ratio,
                            reference=threshold,
                            details=[
                                evidence(
                                    "PRICE_CHANGE", close / previous - 1 if previous else None, None
                                ),
                                evidence("VOLUME", number(row, "Volume"), None),
                                evidence("VOLUME_RATIO", ratio, None),
                                evidence("REFERENCE_VOLUME", number(row, "Vol_SMA_20_Prev"), None),
                            ],
                        )
                    )
        contraction = number(row, "Volume_Contraction_Ratio")
        if (
            params.contraction_ratio is not None
            and contraction is not None
            and pd.notna(row.get("Contraction_Context"))
            and row.get("Contraction_Context") is not None
        ):
            episode(
                "contraction",
                "VOLUME_CONTRACTION",
                _truth(row, "Contraction_Context")
                and contraction is not None
                and contraction <= params.contraction_ratio,
                day,
                evidence_value=contraction,
                reference=params.contraction_ratio,
            )
        sma20, slope, prior_slope = (
            number(row, key) for key in ("SMA_20", "SMA_20_Slope_5", "Previous_SMA20_Slope")
        )
        prior_trend = _truth(row, "Prior_Trend_Context")
        valid = close is not None and sma20 is not None and slope is not None
        weak = bool(valid and prior_trend and close < sma20 and slope <= 0)
        starts_weak = weak and slope < 0 and prior_slope is not None and prior_slope >= 0
        if (
            valid
            and row.get("Prior_Trend_Context") is not None
            and pd.notna(row.get("Prior_Trend_Context"))
        ):
            episode(
                "deceleration",
                "MOMENTUM_DECELERATION",
                weak if "deceleration" in active else starts_weak,
                day,
                evidence_value=close,
                reference=sma20,
                details=[evidence("SMA20_SLOPE_5", slope, 0)],
            )
        accelerates = bool(
            valid
            and prior_trend
            and _truth(row, "Prior_Below_SMA20")
            and close > sma20
            and slope > 0
            and prior_slope is not None
            and prior_slope <= 0
        )
        mode = params.reacceleration_mode
        if mode == "SMA20_TURN_POSITIVE_RETURN":
            accelerates = accelerates and (number(row, "Return_5") or 0) > 0
        elif mode == "SMA20_TURN_HIGH_BREAK":
            accelerates = accelerates and _truth(row, "High_Break_5")
        if mode is not None and accelerates:
            history.append(
                make("MOMENTUM_REACCELERATION", day, event=True, evidence_value=slope, reference=0)
            )

        anchors = []
        for kind, column in [
            ("SMA50", "SMA_50"),
            ("SMA150", "SMA_150"),
            ("SUPERTREND", "SuperTrend_Up"),
        ]:
            value = number(row, column)
            if kind == "SUPERTREND" and number(row, "SuperTrend_Dir") != 1:
                value = None
            if value is not None:
                origins.setdefault(kind, (day, Decimal(str(value))))
                anchors.append((kind, kind, value, None, False, *origins[kind]))
        for context in source_contexts:
            if (
                context.signal.occurred_on > day
                or context.signal.finality != SignalFinality.FINAL
                or context.anchors is None
            ):
                continue
            terminal = context.terminal_on is not None and context.terminal_on <= day
            for kind, value in [
                ("PRIOR_BREAKOUT_LEVEL", context.anchors.breakout_level),
                ("PULLBACK_LOW", context.anchors.pullback_low),
                ("ORIGIN_SUPPORT", context.anchors.origin_support),
            ]:
                if value is not None:
                    identity = f"{context.signal.signal_id}:{kind}"
                    anchors.append(
                        (
                            identity,
                            kind,
                            float(value),
                            context.signal.signal_id,
                            terminal,
                            context.anchors.source_date,
                            value,
                        )
                    )
        atr = number(row, "ATR")
        if (
            close is None
            or atr is None
            or atr <= 0
            or params.break_buffer_atr is None
            or params.reclaim_buffer_atr is None
        ):
            continue
        for identity, kind, value, source, terminal, origin_on, origin_price in anchors:
            code = (
                "BREAKOUT_LEVEL_BREACH"
                if kind == "PRIOR_BREAKOUT_LEVEL"
                else "PULLBACK_LOW_BREACH"
                if kind == "PULLBACK_LOW"
                else "SUPPORT_BREAK"
            )
            metadata = {
                "source_signal_id": source,
                "anchor_id": identity,
                "anchor_type": kind,
                "anchor_origin_on": origin_on,
                "anchor_origin_price": origin_price,
                "source_terminal": terminal,
            }
            if identity not in breached and close < value - params.break_buffer_atr * atr:
                breached[identity] = day
                episode(
                    identity,
                    code,
                    True,
                    day,
                    evidence_value=close,
                    reference=value - params.break_buffer_atr * atr,
                    details=[evidence("ANCHOR_VALUE", value, None), evidence("ATR", atr, None)],
                    **metadata,
                )
            elif identity in breached:
                reclaim = close > value + params.reclaim_buffer_atr * atr
                episode(
                    identity,
                    code,
                    not reclaim,
                    day,
                    evidence_value=close,
                    reference=value + params.reclaim_buffer_atr * atr,
                    details=[evidence("ANCHOR_VALUE", value, None), evidence("ATR", atr, None)],
                    **metadata,
                )
                if reclaim:
                    breached.pop(identity)
                    history.append(
                        make(
                            "BREAKOUT_RECLAIM"
                            if kind == "PRIOR_BREAKOUT_LEVEL"
                            else "SUPPORT_RECLAIM",
                            day,
                            event=True,
                            evidence_value=close,
                            reference=value,
                            **metadata,
                        )
                    )
    return sorted(history, key=lambda item: (item.started_on, item.code, item.observation_id))
