"""Explicit legacy observation replay and exact fixed-price row comparisons.

The reviewed strict anchor default is deliberately separate. No signal policy,
terminal state, count, TTL or risk-level combination belongs here.
"""

from dataclasses import replace

import pandas as pd

from src.tools.technical.chart_analysis.detectors import _combined_finality, _finality
from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    ChartItem,
    FeatureAnchor,
    FixedPriceAnchor,
    SeriesInput,
)


def evaluate_compat_anchor(scope, request, anchors, key, *, feature_resolver):
    if len(anchors) != 1:
        return {}, ()
    anchor = anchors[0]
    frame = scope.primary.raw
    profile = request.parameters["replay_profile"]

    def item(day, values, *, state, kind="EPISODE", status_on=None):
        return ChartItem.create(
            manifest=scope.primary.manifest,
            request=request,
            anchor_id=anchor.id,
            occurred_on=day,
            evaluation_key=key,
            kind=kind,
            confirmed_on=day,
            status_as_of=status_on or day,
            state=state,
            finality="FINAL",
            evidence=values,
        )

    available = max(anchor.origin_on, anchor.available_on)
    if profile == "ENTRY_SHADOW_V1":
        if isinstance(anchor, FeatureAnchor):
            return {}, ()
        rows = []
        for stamp, row in frame.iterrows():
            if stamp.date() >= available:
                close, value = row["Close"], anchor.value
                rows.append(
                    {
                        "on": stamp.date(),
                        "close": close,
                        "value": value,
                        "below": close < value,
                        "at_or_below": close <= value,
                        "above": close > value,
                        "at_or_above": close >= value,
                    }
                )
        fact = item(
            anchor.origin_on,
            {"rows": rows},
            state="OBSERVED",
            kind="STATE",
            status_on=scope.primary.manifest.as_of,
        )
        return {}, (
            replace(
                fact,
                finality=_combined_finality(
                    anchor.finality, *(_finality(scope.primary, row["on"]) for row in rows)
                ),
            ),
        )
    if isinstance(anchor, FixedPriceAnchor) and anchor.finality == "PROVISIONAL":
        return {}, ()
    values = (
        feature_resolver(scope.series_for(anchor.input_role), anchor)
        if isinstance(anchor, FeatureAnchor)
        else pd.Series(float(anchor.value), index=frame.index)
    )
    history = []
    active = None
    break_buffer, reclaim_buffer = (
        request.parameters[k] for k in ("break_buffer_atr", "reclaim_buffer_atr")
    )
    for stamp, row in frame.iterrows():
        day = stamp.date()
        if day < available or _finality(scope.primary, day) != "FINAL":
            continue
        if (
            isinstance(anchor, FeatureAnchor)
            and anchor.active_when == "SUPERTREND_UP"
            and row.get("SuperTrend_Dir") != 1
        ):
            continue
        value, close, atr = values.loc[stamp], row.get("Close"), row.get("ATR")
        if any(x is None or pd.isna(x) for x in (value, close, atr)) or atr <= 0:
            continue
        # Legacy checks only reclaim while already breached, including overlapping buffers.
        reference = (
            value + reclaim_buffer * atr if active is not None else value - break_buffer * atr
        )
        measured = {
            "close": float(close),
            "reference": float(reference),
            "value": float(value),
            "atr": float(atr),
        }
        if active is None:
            if close < reference:
                active = len(history)
                history.append(
                    item(
                        day,
                        {"origin": measured, "current": measured, "updated": False},
                        state="BREACHED",
                    )
                )
        else:
            old = history[active]
            reclaimed = close > reference
            history[active] = replace(
                old,
                status_as_of=day,
                state="RESOLVED" if reclaimed else "BREACHED",
                evidence={
                    "origin": old.evidence["origin"],
                    "current": measured,
                    "updated": True,
                    "ended_on": day if reclaimed else None,
                },
            )
            if reclaimed:
                history.append(
                    item(
                        day,
                        {"close": float(close), "value": float(value)},
                        state="RECLAIMED",
                        kind="EVENT",
                    )
                )
                active = None
    return {}, tuple(history)


def evaluate_legacy_anchor_with_preview(scope, request, anchors, key, *, feature_resolver):
    final = evaluate_compat_anchor(scope, request, anchors, key, feature_resolver=feature_resolver)[
        1
    ]
    frame = scope.primary.raw
    if len(frame) and _finality(scope.primary, frame.index[-1].date()) == "PROVISIONAL":
        day = frame.index[-1].date()
        finalities = {
            stamp.date(): (
                "FINAL" if stamp.date() == day else _finality(scope.primary, stamp.date())
            )
            for stamp in frame.index
        }
        preview_scope = CalculationScope(
            SeriesInput(replace(scope.primary.manifest, finality=finalities), frame), scope.related
        )
        preview_anchors = tuple(
            replace(a, finality="FINAL")
            if isinstance(a, FixedPriceAnchor) and a.available_on == day
            else a
            for a in anchors
        )
        preview = evaluate_compat_anchor(
            preview_scope, request, preview_anchors, key, feature_resolver=feature_resolver
        )[1]
        known = {item.id for item in final}
        final += tuple(
            replace(item, finality="PROVISIONAL")
            for item in preview
            if item.id not in known and item.occurred_on == day
        )
    return {}, final
