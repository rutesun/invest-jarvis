"""Focused I1/I2 regressions: prerequisites and actual anchor dependencies."""

from importlib import import_module

import pytest

from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    FeatureAnchor,
    FixedPriceAnchor,
)
from src.tools.technical.chart_analysis.registry import rule_request
from src.tools.technical.chart_analysis.service import AnalysisRequestContext
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


@pytest.mark.parametrize(
    "rule,role,column",
    [
        ("chart.pivot.span3", "instrument", "High"),
        ("chart.pivot.span3", "instrument", "Low"),
        ("chart.rs", "instrument", "Close"),
        ("chart.rs", "market", "Close"),
        ("chart.market.regime", "market", "Close"),
    ],
)
def test_missing_raw_prerequisite_returns_typed_unavailable(rule, role, column):
    frame = bars([100] * 30)
    primary = scope_for(frame.drop(columns=column) if role == "instrument" else frame).primary
    market_frame = frame.drop(columns=column) if role == "market" else frame
    market = scope_for(market_frame).primary
    result = AnalysisRequestContext().get(
        CalculationScope(primary, {"market": market}), (rule_request(rule),)
    )
    assert len(result.items) == 1
    assert result.items[0].state == "UNAVAILABLE"
    assert result.items[0].evidence["reasons"] == ("INPUT_MISSING",)


@pytest.mark.parametrize(
    "code,close", [("UP_VOLUME_EXPANSION", 101), ("DOWN_VOLUME_EXPANSION", 99)]
)
def test_supplied_ohlcv_volume_observation_does_not_require_momentum_features(code, close):
    frame = bars([100] * 29 + [close])
    frame.loc[frame.index[-1], "Volume"] = 15.0
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    result = AnalysisRequestContext().get(
        scope, (rule_request("OBSERVATION_V1", {"code": code, "threshold": 1.5}),)
    )
    assert len(result.items) == 1
    assert result.items[0].state == "RESOLVED"
    assert result.items[0].occurred_on == frame.index[-1].date()
    assert result.items[0].evidence["current"]["Volume_Ratio_Prev20"] == 1.5


@pytest.mark.parametrize(
    "rule,parameters",
    [
        ("OBSERVATION_V1", {"code": "VOLUME_CONTRACTION", "threshold": 0.7}),
        ("chart.momentum.deceleration", {}),
        ("chart.momentum.reacceleration", {"mode": "SMA20_TURN"}),
    ],
)
def test_observation_reports_missing_selected_prerequisite(rule, parameters):
    scope = scope_for(bars([100] * 30), feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    result = AnalysisRequestContext().get(scope, (rule_request(rule, parameters),))
    assert result.items[0].state == "UNAVAILABLE"
    assert result.items[0].evidence["reasons"] == ("INPUT_MISSING",)


def test_supplied_contraction_without_sma20_uses_only_its_selected_features():
    frame = bars([100] * 30)
    frame["Contraction_Context"] = True
    frame["Volume_Contraction_Ratio"] = 0.6
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    result = AnalysisRequestContext().get(
        scope, (rule_request("OBSERVATION_V1", {"code": "VOLUME_CONTRACTION", "threshold": 0.7}),)
    )
    assert len(result.items) == 1 and result.items[0].state == "ACTIVE"


def selected_anchor(scope, kind="rolling", active_when="ALWAYS"):
    frame = scope.primary.raw
    common = {
        "id": "support",
        "kind": "SUPPORT",
        "origin_on": frame.index[2].date(),
        "available_on": frame.index[2].date(),
        "origin_value": 100.0,
        "source_id": "test",
    }
    if kind == "fixed":
        return FixedPriceAnchor(**common, value=100.0, finality="FINAL")
    return FeatureAnchor(
        **common,
        input_role="instrument",
        feature_key="Close" if kind == "raw-close" else "SMA_3",
        feature_version=scope.primary.manifest.feature_version
        if kind == "raw-close"
        else "SMA_ROLLING_V1",
        active_when=active_when,
    )


@pytest.mark.parametrize("feature_version", ["CHART_FEATURE_V1", "LEGACY_FEATURE_AD880AF"])
@pytest.mark.parametrize("kind", ["fixed", "rolling", "raw-close"])
def test_zero_buffer_anchor_uses_raw_close_without_unnecessary_feature_provider(
    monkeypatch, feature_version, kind
):
    module = import_module("src.tools.technical.chart_analysis.evaluators")
    scope = scope_for(bars([100] * 29 + [90]), feature_version=feature_version)

    def forbidden(*args, **kwargs):
        pytest.fail("zero-buffer raw price anchor executed an unused feature provider")

    monkeypatch.setattr(module.feature_api, "calculate_features", forbidden)
    monkeypatch.setattr(module, "prepare_legacy_frame", forbidden)
    ctx = AnalysisRequestContext()
    anchor = selected_anchor(scope, kind)
    first = ctx.get(scope, (rule_request("chart.anchor.break_reclaim"),), (anchor,))
    if kind != "raw-close":
        assert first.items[0].state == "BREACHED"
    original = module.feature_api.feature_provider_identity

    def changed(fv):
        return {**original(fv), "backend": "unused-provider-revision"}

    monkeypatch.setattr(module.feature_api, "feature_provider_identity", changed)
    second = ctx.get(scope, (rule_request("chart.anchor.break_reclaim"),), (anchor,))
    assert first is second


def test_actual_supertrend_activation_provider_is_reported_and_changes_keys(monkeypatch):
    module = import_module("src.tools.technical.chart_analysis.evaluators")
    close = [100 + 0.1 * i for i in range(240)]
    close[-1] = 123.0
    scope = scope_for(bars(close), feature_version="LEGACY_FEATURE_AD880AF")
    anchor = selected_anchor(scope, active_when="SUPERTREND_UP")
    rule = rule_request("chart.anchor.break_reclaim")
    original_prepare = module.prepare_legacy_frame
    measured_directions = []

    def counted(series):
        frame = original_prepare(series)
        measured_directions.append(frame["SuperTrend_Dir"].iloc[-1])
        return frame

    monkeypatch.setattr(module, "prepare_legacy_frame", counted)
    ctx = AnalysisRequestContext()
    first = ctx.get(scope, (rule,), (anchor,))
    assert measured_directions == [1.0]
    assert first.items[0].state == "BREACHED"
    identity = module.provider_identity(scope, rule, (anchor,))
    activation = identity["providers"]["instrument:activation"]
    assert activation["feature_version"] == "LEGACY_FEATURE_AD880AF"
    assert "pandas-ta" in activation["packages"]
    assert identity["providers"]["instrument:price"]["feature_version"] == "SMA_ROLLING_V1"
    original_identity = module.feature_api.feature_provider_identity

    def changed(fv):
        result = original_identity(fv)
        if fv == "LEGACY_FEATURE_AD880AF":
            result["backend"] += "/other-build"
        return result

    monkeypatch.setattr(module.feature_api, "feature_provider_identity", changed)
    second = ctx.get(scope, (rule,), (anchor,))
    assert measured_directions == [1.0, 1.0]
    assert first.analysis_id != second.analysis_id
    assert first.items[0].evaluation_key != second.items[0].evaluation_key
    assert first.items[0].id == second.items[0].id


def test_nonzero_anchor_buffer_records_actual_atr_provider_separately():
    module = import_module("src.tools.technical.chart_analysis.evaluators")
    scope = scope_for(bars([100] * 29 + [90]))
    anchor = selected_anchor(scope, "fixed")
    rule = rule_request(
        "chart.anchor.break_reclaim", {"break_buffer_atr": 1.0, "reclaim_buffer_atr": 0.5}
    )
    identity = module.provider_identity(scope, rule, (anchor,))
    assert identity["providers"]["instrument:ATR"]["feature_version"] == "CHART_FEATURE_V1"
    assert identity["providers"]["instrument:Close"]["backend"] == "raw-column"
    result = AnalysisRequestContext().get(scope, (rule,), (anchor,))
    assert result.items[0].state == "BREACHED"
