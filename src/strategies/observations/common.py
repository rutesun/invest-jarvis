"""Translate strategy source metadata into neutral common observation descriptors."""

import pandas as pd

from src.strategies.models import BarFinality, SignalFinality
from src.strategies.swing_w150.common import feature_scope
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.features import SUPPLIED_VERSION
from src.tools.technical.chart_analysis.models import FeatureAnchor, FixedPriceAnchor
from src.tools.technical.chart_analysis.registry import rule_request


def observation_rules(params):
    rules = [
        rule_request("OBSERVATION_V1", {"code": code, "frame_policy": "SUPPLIED_AS_IS"})
        for code in ("HIGHER_LOW", "HIGHER_HIGH", "LOWER_HIGH", "LOWER_LOW")
    ]
    for code, threshold in (
        ("UP_VOLUME_EXPANSION", params.up_volume_ratio),
        ("DOWN_VOLUME_EXPANSION", params.down_volume_ratio),
        ("VOLUME_CONTRACTION", params.contraction_ratio),
    ):
        rules.append(
            rule_request(
                "OBSERVATION_V1",
                {"code": code, "threshold": threshold, "frame_policy": "SUPPLIED_AS_IS"},
            )
        )
    rules.append(rule_request("chart.momentum.deceleration", {"frame_policy": "SUPPLIED_AS_IS"}))
    if params.reacceleration_mode is not None:
        rules.append(
            rule_request(
                "chart.momentum.reacceleration",
                {"mode": params.reacceleration_mode, "frame_policy": "SUPPLIED_AS_IS"},
            )
        )
    if params.break_buffer_atr is not None and params.reclaim_buffer_atr is not None:
        rules.append(
            rule_request(
                "chart.anchor.break_reclaim",
                {
                    "break_buffer_atr": params.break_buffer_atr,
                    "reclaim_buffer_atr": params.reclaim_buffer_atr,
                    "replay_profile": "LEGACY_OBSERVATION_V1",
                },
            )
        )
    return tuple(rules)


def observation_anchors(features, source_contexts):
    frame = features.frame
    anchors = []
    for kind, column in (
        ("SMA50", "SMA_50"),
        ("SMA150", "SMA_150"),
        ("SUPERTREND", "SuperTrend_Up"),
    ):
        if column not in frame:
            continue
        for i, (stamp, row) in enumerate(frame.iterrows()):
            value = row[column]
            if (
                (
                    features.finalities[i] != BarFinality.FINAL
                    and not (
                        i == len(frame) - 1 and features.finalities[i] == BarFinality.PROVISIONAL
                    )
                )
                or value is None
                or pd.isna(value)
                or (kind == "SUPERTREND" and row.get("SuperTrend_Dir") != 1)
            ):
                continue
            day = stamp.date()
            anchors.append(
                FeatureAnchor(
                    kind,
                    kind,
                    day,
                    day,
                    float(value),
                    "instrument",
                    column,
                    SUPPLIED_VERSION,
                    "SUPERTREND_UP" if kind == "SUPERTREND" else "ALWAYS",
                    "",
                )
            )
            break
    for context in source_contexts:
        if (
            context.signal.finality == SignalFinality.PROVISIONAL
            and context.signal.occurred_on > frame.index[-1].date()
        ):
            continue
        if context.signal.occurred_on > frame.index[-1].date():
            raise ValueError("Future source anchor is unavailable at as_of")
        if context.anchors is None or (
            context.signal.finality != SignalFinality.FINAL
            and not (
                context.signal.occurred_on == frame.index[-1].date()
                and features.finalities[-1] == BarFinality.PROVISIONAL
            )
        ):
            continue
        source = context.anchors
        for kind, value in (
            ("PRIOR_BREAKOUT_LEVEL", source.breakout_level),
            ("PULLBACK_LOW", source.pullback_low),
            ("ORIGIN_SUPPORT", source.origin_support),
        ):
            if value is not None:
                identity = f"{context.signal.signal_id}:{kind}"
                anchors.append(
                    FixedPriceAnchor(
                        identity,
                        kind,
                        source.source_date,
                        context.signal.occurred_on,
                        float(value),
                        float(value),
                        context.signal.finality.value.upper(),
                        context.signal.signal_id,
                    )
                )
    return tuple(anchors)


def observation_analysis(
    ticker, features, source_contexts, params, *, context=None, extra_anchors=()
):
    anchors = (*observation_anchors(features, source_contexts), *extra_anchors)
    return (context or AnalysisRequestContext()).get(
        feature_scope(ticker, features), observation_rules(params), anchors
    )


class ObservationHistory(list):
    """List-compatible public result retaining only request-local fact snapshots."""

    def __init__(self, values=(), *, common_analyses=(), fact_selections=()):
        super().__init__(values)
        self.common_analyses = tuple(common_analyses)
        self.fact_selections = tuple(fact_selections)
