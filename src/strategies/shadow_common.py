"""Exact Decimal source-anchor facts, without research policy state."""

import pandas as pd

from src.strategies.swing_w150.common import frame_scope, validate_analysis
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.models import FixedPriceAnchor
from src.tools.technical.chart_analysis.registry import rule_request


def shadow_request():
    return rule_request(
        "chart.anchor.break_reclaim",
        {"break_buffer_atr": 0, "reclaim_buffer_atr": 0, "replay_profile": "ENTRY_SHADOW_V1"},
    )


def shadow_scope(bundle):
    frame = pd.DataFrame(
        {"Close": [bar.close for bar in bundle.instrument.bars]},
        index=pd.DatetimeIndex([bar.session_date for bar in bundle.instrument.bars]),
    )
    return frame_scope(
        bundle.ticker,
        frame,
        finalities=[bar.finality for bar in bundle.instrument.bars],
        coverage=bundle.instrument.coverage,
        bundle=bundle,
    )


def shadow_anchors(source, parameters):
    if source.source_type == "TREND_BREAKOUT_ENTRY":
        values = {"breakout": source.breakout_level}
        if source.atr_at_signal is not None:
            values["adverse"] = (
                source.signal_price - parameters.adverse_atr_multiple * source.atr_at_signal
            )
    else:
        values = {"origin": source.origin_support, "pullback": source.pullback_low}
        if source.origin_support is not None and source.pullback_low is not None:
            values["combined"] = max(source.origin_support, source.pullback_low)
    return tuple(
        FixedPriceAnchor(
            f"{source.source_id}:shadow:{kind}",
            kind,
            source.source_date,
            source.source_date,
            value,
            value,
            source.anchor_finality.value.upper(),
            source.source_id,
        )
        for kind, value in values.items()
        if value is not None
    )


def shadow_analysis(bundle, anchors, parameters, *, context=None, extra_anchors=()):
    return (context or AnalysisRequestContext()).get(
        shadow_scope(bundle),
        (shadow_request(),),
        (*shadow_anchors(anchors, parameters), *extra_anchors),
    )


def shadow_rows(analysis, bundle, anchors, parameters):
    validate_analysis(analysis, shadow_scope(bundle), (shadow_request(),))
    required = shadow_anchors(anchors, parameters)
    if not all(anchor in analysis.requested_anchors for anchor in required):
        raise ValueError("common_analysis shadow anchor inventory mismatch")
    selected = {anchor.id: anchor for anchor in required}
    items = [
        item
        for item in analysis.items
        if item.rule_id == "chart.anchor.break_reclaim"
        and item.parameter_id == shadow_request().parameter_id
        and item.anchor_id in selected
    ]
    if {item.anchor_id for item in items} != set(selected):
        raise ValueError("common_analysis shadow anchor inventory mismatch")
    rows = {}
    for item in items:
        anchor = selected[item.anchor_id]
        if any(row["value"] != anchor.value for row in item.evidence["rows"]):
            raise ValueError("common_analysis shadow fixed anchor mismatch")
        rows[anchor.kind] = {row["on"]: row for row in item.evidence["rows"]}
    return rows, items
