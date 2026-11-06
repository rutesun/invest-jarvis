"""Common RS, anchor and confirmed pivot evaluators; no consumer policies."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite

import pandas as pd

from src.tools.technical.chart_analysis._legacy_playbook import relative_strength_values
from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    ChartAnchor,
    ChartItem,
    FeatureAnchor,
    FeatureValue,
    FixedPriceAnchor,
    RuleRequest,
    SeriesInput,
)
from src.tools.technical.chart_analysis.registry import COMPAT_VERSION, RS_ALIGNMENT


def _finality(series: SeriesInput, day) -> str:
    finality = series.manifest.finality
    return finality if isinstance(finality, str) else finality.get(day, "UNKNOWN")


def _finite(value) -> bool:
    return pd.notna(value) and isfinite(float(value))


def _combined_finality(*values: str) -> str:
    if not values or any(value not in ("FINAL", "PROVISIONAL") for value in values):
        return "UNKNOWN"
    return "PROVISIONAL" if "PROVISIONAL" in values else "FINAL"


def _sma_period(anchor: FeatureAnchor) -> int | None:
    match = re.fullmatch(r"SMA_([1-9][0-9]*)", anchor.feature_key)
    return int(match[1]) if anchor.feature_version == "SMA_ROLLING_V1" and match else None


def _sma_dependency_index(
    series: SeriesInput, anchor: FeatureAnchor, evaluation_index: pd.DatetimeIndex
) -> pd.DatetimeIndex:
    """Include the actual rolling seed even when its role starts before primary."""
    period = _sma_period(anchor)
    index = series.raw.index
    available_on = max(anchor.origin_on, anchor.available_on)
    eligible = evaluation_index[[day.date() >= available_on for day in evaluation_index]]
    positions = index.get_indexer(eligible)
    used = positions[positions >= 0]
    if period is None or not len(used):
        return index[:0]
    return index[max(0, min(used) - period + 1) : max(used) + 1]


def resolve_anchor_feature(series: SeriesInput, anchor: FeatureAnchor) -> pd.Series:
    """Resolve explicit strict/legacy/supplied or SMA_ROLLING_V1 providers."""
    frame = series.raw
    period = _sma_period(anchor)
    if period is not None:
        return frame["Close"].rolling(period).mean()
    if anchor.feature_version != series.manifest.feature_version:
        raise ValueError("FeatureAnchor feature_version does not match feature provider")
    if anchor.feature_version in ("CHART_FEATURE_V1", "LEGACY_FEATURE_AD880AF"):
        from src.tools.technical.chart_analysis.evaluators import DetectorFactory

        return DetectorFactory().anchor_feature(series, anchor)
    if anchor.feature_key not in frame:
        raise NotImplementedError(f"No feature provider for {anchor.feature_key}")
    return frame[anchor.feature_key]


def evaluate_rs(
    scope: CalculationScope,
    request: RuleRequest,
    anchors: tuple[ChartAnchor, ...],
    key: str,
) -> tuple[Mapping[str, FeatureValue], tuple[ChartItem, ...]]:
    if (
        request.rule_version != COMPAT_VERSION
        or request.alignment_version != RS_ALIGNMENT
        or request.input_roles != ("instrument", "market")
        or request.parameters
    ):
        raise ValueError("Unsupported chart.rs contract")
    primary, market = scope.primary, scope.series_for("market")
    primary_frame, market_frame = primary.raw, market.raw
    result = relative_strength_values(primary_frame, market_frame)
    if primary_frame.empty:
        return {}, ()
    first = primary_frame.index[0].date()
    stock_close, market_close = primary_frame["Close"].dropna(), market_frame["Close"].dropna()
    aligned = stock_close.index.intersection(market_close.index)
    evaluated_on = aligned[-1].date() if len(aligned) else None
    finality = _combined_finality(
        *(
            value
            for day in aligned
            for value in (_finality(primary, day.date()), _finality(market, day.date()))
        )
    )
    item = ChartItem.create(
        manifest=primary.manifest,
        request=request,
        anchor_id=None,
        occurred_on=first,
        evaluation_key=key,
        kind="STATE",
        confirmed_on=evaluated_on,
        status_as_of=primary.manifest.as_of,
        state="STRONG" if result["strong"] else "WEAK",
        finality=finality,
        evidence={**result, "evaluated_on": evaluated_on},
    )
    return {}, (item,)


@dataclass(frozen=True)
class _AnchorReplay:
    state: str = "CLEAR"
    started_on: date | None = None
    current_value: float | None = None
    transitions: tuple[dict, ...] = ()


def _anchor_step(
    previous: _AnchorReplay,
    day: date,
    row: pd.Series,
    value: float,
    *,
    active: bool,
    available_on: date,
    buffers: list[float],
) -> _AnchorReplay:
    # A skipped feature evaluation preserves the prior state and its origin.
    current = replace(previous, current_value=None)
    if day < available_on or not active or not _finite(value) or not _finite(row["Close"]):
        return current
    atr = row.get("ATR") if any(buffers) else 0.0
    if not _finite(atr):
        return current
    current = replace(current, current_value=float(value))
    close, next_state, started_on = float(row["Close"]), current.state, current.started_on
    if close < value - buffers[0] * atr:
        next_state = "BREACHED"
        started_on = started_on or day
    elif current.state == "BREACHED" and close > value + buffers[1] * atr:
        next_state = "RECLAIMED"
    transitions = current.transitions
    if next_state != current.state:
        transitions += ({"on": day, "state": next_state, "value": float(value)},)
    return replace(current, state=next_state, started_on=started_on, transitions=transitions)


def evaluate_anchor(
    scope: CalculationScope,
    request: RuleRequest,
    anchors: tuple[ChartAnchor, ...],
    key: str,
    *,
    feature_resolver=None,
    frame_resolver=None,
) -> tuple[Mapping[str, FeatureValue], tuple[ChartItem, ...]]:
    if request.rule_version != "OBSERVATION_PARAMS_V1" or request.alignment_version != "SESSION_V1":
        raise ValueError("Unsupported chart.anchor.break_reclaim contract")
    if not anchors:
        return {}, ()
    if len(anchors) != 1:
        raise ValueError("Anchor evaluator requires one independently keyed anchor")
    anchor = anchors[0]
    if "instrument" not in request.input_roles:
        raise ValueError("Anchor evaluation requires instrument input_role")
    expected_parameters = {"break_buffer_atr", "reclaim_buffer_atr"}
    if set(request.parameters) != expected_parameters:
        raise ValueError("Anchor buffers must be explicitly selected")
    buffers = [request.parameters[name] for name in ("break_buffer_atr", "reclaim_buffer_atr")]
    if any(value is None or not _finite(value) or value < 0 for value in buffers):
        raise ValueError("Anchor buffers must be finite and nonnegative")
    primary = scope.primary
    frame = primary.raw
    if any(buffers) and frame_resolver:
        # Price replay consumes raw Close. Only selected ATR buffers need the
        # feature provider; zero-buffer Fixed/rolling anchors must not invoke it.
        atr_frame = frame_resolver(primary)
        frame["ATR"] = atr_frame.get("ATR")
    if isinstance(anchor, FixedPriceAnchor):
        values = pd.Series(anchor.value, index=frame.index)
        feature_input = primary
        direction = None
    else:
        feature_input = scope.series_for(anchor.input_role)
        values = (feature_resolver or resolve_anchor_feature)(feature_input, anchor).reindex(
            frame.index
        )
        direction = None
        if anchor.active_when == "SUPERTREND_UP":
            activation_frame = (
                frame_resolver(feature_input) if frame_resolver else feature_input.raw
            )
            direction = activation_frame.get("SuperTrend_Dir")
            if direction is None:
                raise ValueError("SUPERTREND_UP requires SuperTrend_Dir from feature input")
            direction = direction.reindex(frame.index)
    available_on = max(anchor.origin_on, anchor.available_on)
    dependency_finalities = {}
    for timestamp in frame.index:
        day = timestamp.date()
        if isinstance(anchor, FixedPriceAnchor):
            source_finality = anchor.finality if day >= available_on else "FINAL"
        else:
            source_finality = _finality(feature_input, day)
        dependency_finalities[day] = _combined_finality(source_finality, _finality(primary, day))
    if isinstance(anchor, FeatureAnchor):
        seed_index = _sma_dependency_index(feature_input, anchor, frame.index)
        calculated_price = anchor.feature_version in (
            "CHART_FEATURE_V1",
            "LEGACY_FEATURE_AD880AF",
        ) and anchor.feature_key not in ("Open", "High", "Low", "Close", "Volume")
        calculated_activation = (
            anchor.active_when == "SUPERTREND_UP"
            and feature_input.manifest.feature_version
            in ("CHART_FEATURE_V1", "LEGACY_FEATURE_AD880AF")
        )
        if calculated_price or calculated_activation:
            seed_index = feature_input.raw.index[feature_input.raw.index <= frame.index[-1]]
        for timestamp in seed_index:
            day = timestamp.date()
            dependency_finalities[day] = _combined_finality(
                dependency_finalities.get(day, "FINAL"), _finality(feature_input, day)
            )
    first_nonfinal = next(
        (day for day in sorted(dependency_finalities) if dependency_finalities[day] != "FINAL"),
        None,
    )
    boundary = next(
        (
            i
            for i, timestamp in enumerate(frame.index)
            if first_nonfinal is not None and timestamp.date() >= first_nonfinal
        ),
        len(frame),
    )
    has_suffix = first_nonfinal is not None
    can_preview = (
        has_suffix
        and boundary > 0
        and boundary == len(frame) - 1
        and frame.index[boundary].date() == first_nonfinal
        and dependency_finalities[first_nonfinal] == "PROVISIONAL"
    )
    incomplete = has_suffix and not can_preview

    def step(replay: _AnchorReplay, position: int) -> _AnchorReplay:
        timestamp = frame.index[position]
        active = not (
            isinstance(anchor, FeatureAnchor)
            and anchor.active_when == "SUPERTREND_UP"
            and (not _finite(direction.loc[timestamp]) or direction.loc[timestamp] != 1)
        )
        return _anchor_step(
            replay,
            timestamp.date(),
            frame.iloc[position],
            values.loc[timestamp],
            active=active,
            available_on=available_on,
            buffers=buffers,
        )

    final = _AnchorReplay()
    for position in range(boundary):
        final = step(final, position)
    # This value is immutable: preview transitions cannot mutate the confirmed seed.
    preview = step(final, boundary) if can_preview else None
    current = preview or final
    if current.started_on is None and not incomplete:
        return {}, ()
    final_as_of = frame.index[boundary - 1].date() if boundary else None
    incomplete_on = first_nonfinal if incomplete else None
    item = ChartItem.create(
        manifest=primary.manifest,
        request=request,
        anchor_id=anchor.id,
        occurred_on=current.started_on or anchor.origin_on,
        evaluation_key=key,
        kind="EPISODE",
        confirmed_on=final.started_on,
        status_as_of=primary.manifest.as_of,
        state="INCOMPLETE_PREFIX" if incomplete else current.state,
        finality="UNKNOWN" if incomplete else "PROVISIONAL" if preview else "FINAL",
        evidence={
            "origin_on": anchor.origin_on,
            "origin_price": anchor.origin_value,
            "current_value": None if incomplete else current.current_value,
            "source_id": anchor.source_id,
            "transitions": final.transitions,
            "final_state": final.state,
            "final_started_on": final.started_on,
            "final_as_of": final_as_of,
            "final_transitions": final.transitions,
            "preview_state": preview.state if preview else None,
            "preview_started_on": preview.started_on if preview else None,
            "preview_transitions": preview.transitions[len(final.transitions) :] if preview else (),
            "incomplete_on": incomplete_on,
        },
    )
    return {}, (item,)


def evaluate_pivots(scope, request, anchors, key):
    from dataclasses import asdict

    from src.tools.technical.chart_analysis.pivots import confirmed_pivot_events

    frame = scope.primary.raw
    mask = (
        [_finality(scope.primary, day.date()) == "FINAL" for day in frame.index]
        if request.parameters["final_mask"]
        else None
    )
    events = confirmed_pivot_events(
        frame["High"].to_numpy(float), frame["Low"].to_numpy(float), final_mask=mask
    )
    return {}, tuple(
        ChartItem.create(
            manifest=scope.primary.manifest,
            request=request,
            anchor_id=event.pivot_type,
            occurred_on=frame.index[event.pivot_index].date(),
            confirmed_on=frame.index[event.confirmed_index].date(),
            evaluation_key=key,
            kind="EVENT",
            status_as_of=scope.primary.manifest.as_of,
            state=event.relation or event.pivot_type,
            finality="FINAL"
            if mask is not None
            else _combined_finality(
                *(
                    _finality(scope.primary, day.date())
                    for day in frame.index[: event.confirmed_index + 1]
                )
            ),
            evidence=asdict(event),
        )
        for event in events
    )


def default_evaluator_factory():
    """Create complete catalog evaluators sharing only this request's calculations."""
    from src.tools.technical.chart_analysis.evaluators import default_evaluator_factory as create

    return create()


def detect_items(scope, rules, *, anchors=()):
    """One-shot request; use AnalysisRequestContext for unions and retained FactRefs."""
    from src.tools.technical.chart_analysis.service import AnalysisRequestContext

    return AnalysisRequestContext().get(scope, tuple(rules), tuple(anchors)).items
