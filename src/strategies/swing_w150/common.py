"""Explicit request-local SWING fact scopes and excluded reference transport."""

from dataclasses import replace

import pandas as pd

from src.storage.canonical import canonical_hash
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.features import LEGACY_VERSION, SUPPLIED_VERSION
from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    FactRef,
    FactSelection,
    InputManifest,
    SeriesInput,
    content_hash,
)
from src.tools.technical.chart_analysis.registry import rule_request
from src.tools.technical.context import validate_common_requests


def frame_scope(
    ticker,
    frame,
    *,
    finalities=(),
    coverage=None,
    feature_version=SUPPLIED_VERSION,
    source_manifest=None,
    bundle=None,
):
    manifest = InputManifest(
        ticker=ticker,
        exchange="UNSPECIFIED",
        as_of=frame.index[-1].date(),
        origin=str(frame.index[0].date()),
        input_profile=bundle.profile_version if bundle is not None else "SWING_SUPPLIED_V1",
        feature_version=feature_version,
        input_hash="",
        adjustment_policy="AS_SUPPLIED",
        calendar_version=canonical_hash("jarvis:swing-calendar:v1", bundle.exchange_sessions)
        if bundle is not None
        else "AS_SUPPLIED",
        finality={
            stamp.date(): value.value.upper()
            for stamp, value in zip(frame.index, finalities, strict=False)
        }
        if finalities
        else {stamp.date(): "FINAL" for stamp in frame.index},
        coverage=coverage.model_dump(mode="python") if coverage is not None else {"complete": True},
    )
    if source_manifest is not None:
        manifest = replace(
            manifest,
            input_profile=source_manifest.input_profile,
            calendar_version=source_manifest.calendar_version,
            adjustment_policy=source_manifest.adjustment_policy,
            exchange=source_manifest.exchange,
            coverage=source_manifest.coverage if coverage is None else manifest.coverage,
        )
    return CalculationScope(SeriesInput(manifest, frame), {})


def raw_rules(params):
    return (
        rule_request(
            "legacy.indicators",
            {
                "frame_policy": "SWING_FEATURES",
                "direction_lookback": params.direction_lookback_bars,
                "trend_breakout_lookback": params.trend_breakout_lookback,
                "deep_recovery_lookback": params.deep_recovery_breakout_lookback,
            },
        ),
    )


def raw_swing_analysis(
    raw, params, *, ticker="UNSPECIFIED", finalities=(), coverage=None, context=None, bundle=None
):
    scope = frame_scope(
        ticker,
        raw,
        finalities=finalities,
        coverage=coverage,
        feature_version=LEGACY_VERSION,
        bundle=bundle,
    )
    return (context or AnalysisRequestContext()).get(scope, raw_rules(params))


def swing_rules(params, *, replay=False):
    options = {
        "frame_policy": "SUPPLIED_AS_IS",
        "volume_multiple": params.structure_breakdown_volume_multiple,
        "weak_close_location": params.structure_weak_close_location,
        "direction_lookback": params.direction_lookback_bars,
        "trend_volume_multiple": params.trend_breakout_volume_multiple,
        "signal_profile": "V1_REPLAY" if replay else "V2_SIGNAL",
    }
    return (
        rule_request(
            "chart.close_breakout.strict",
            {
                "frame_policy": "SUPPLIED_AS_IS",
                "lookback": params.trend_breakout_lookback,
                "reference_column": "High_50_Prev" if replay else "Trend_Breakout_High_Prev",
                "direction_lookback": params.direction_lookback_bars,
                "volume_multiple": params.trend_breakout_volume_multiple,
                "comparison_profile": "V1_REPLAY" if replay else "V2_SIGNAL",
            },
        ),
        rule_request("chart.structure_breakdown.swing", options),
        rule_request("chart.deep_recovery.swing", options),
        rule_request("chart.pivot.span3", {"final_mask": True}),
    )


def feature_scope(ticker, features):
    manifest = features.common_analyses[0].manifest if features.common_analyses else None
    return frame_scope(
        ticker,
        features.frame,
        finalities=features.finalities,
        coverage=features.coverage,
        source_manifest=manifest,
    )


def swing_analysis(ticker, features, params, *, replay=False, context=None):
    return (context or AnalysisRequestContext()).get(
        feature_scope(ticker, features),
        swing_rules(params, replay=replay),
    )


def validate_analysis(analysis, scope, rules):
    if analysis.manifest != scope.primary.manifest or analysis.dependencies:
        raise ValueError("common_analysis does not match SWING evaluation scope")
    validate_common_requests(analysis, rules)


def request_identity(request):
    return request.rule_id, request.rule_version, request.parameter_id


def requested_items(analysis, rules):
    requested = {request_identity(rule) for rule in rules}
    return tuple(item for item in analysis.items if request_identity(item) in requested)


def row_frame(analysis, request):
    evidence = next(item.evidence for item in requested_items(analysis, (request,)))
    rows = evidence["rows"]
    result = pd.DataFrame(
        [dict(row["values"]) for row in rows], index=pd.DatetimeIndex([row["on"] for row in rows])
    )
    return result.astype(dict(evidence["dtypes"]))


def selections(analysis, rules, *, reason="SWING_FACT_CONSUMED"):
    used = {request_identity(rule) for rule in rules}
    return tuple(
        FactSelection(
            FactRef(analysis.analysis_id, item.id),
            request_identity(item) in used and item.state != "UNAVAILABLE",
            reason if request_identity(item) in used else "SWING_RULE_NOT_USED",
        )
        for item in analysis.items
    )


def validate_frame_analysis(analysis, frame, rules, *, feature_version=SUPPLIED_VERSION):
    manifest = analysis.manifest
    if (
        frame.empty
        or manifest.feature_version != feature_version
        or manifest.input_hash != content_hash(frame)
        or manifest.as_of != frame.index[-1].date()
        or manifest.origin != str(frame.index[0].date())
    ):
        raise ValueError("common_analysis does not match SWING frame scope")
    validate_common_requests(analysis, rules)
