"""Quality's published weights, missing-axis propagation, and history boundary."""

from dataclasses import replace
from importlib import import_module
from math import log, sqrt

import numpy as np
import pytest

from src.tools.technical.chart_analysis.models import FeatureValue, RuleRequest
from src.tools.technical.chart_analysis.registry import rule_request
from src.tools.technical.chart_analysis.service import AnalysisRequestContext
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


def api():
    return import_module("src.tools.technical.chart_analysis.quality")


def analysis_for(frame=None, **kwargs):
    if frame is None:
        frame = bars(100 + np.arange(252) * 0.05 + np.sin(np.arange(252)))
    return AnalysisRequestContext().get(
        scope_for(frame, **kwargs), (rule_request("chart.features.strict"),)
    )


def score(analysis=None):
    return api().score_quality(analysis or analysis_for(), parameters=api().QualityParameters())


def with_features(analysis, **values):
    return replace(
        analysis,
        features={
            **analysis.features,
            **{
                key: value if isinstance(value, FeatureValue) else FeatureValue(value, "READY")
                for key, value in values.items()
            },
        },
    )


def test_strict_material_request_exposes_actual_features_and_preserves_identity():
    analysis = analysis_for()
    assert analysis.features["History_Bars"].value == 252
    assert analysis.features["SMA_200_Lag20"].status == "READY"
    assert analysis.items == ()
    from src.tools.technical.chart_analysis.evaluators import provider_identity
    from src.tools.technical.chart_analysis.features import feature_provider_identity

    scope = scope_for(bars(list(range(100, 352))))
    request = rule_request("chart.features.strict")
    assert provider_identity(scope, request) == {
        "providers": {"instrument": feature_provider_identity("CHART_FEATURE_V1")}
    }
    context = AnalysisRequestContext()
    first = context.get(scope, (request,))
    assert context.get(scope, (request, request)) is first
    wrong = replace(request, parameters={"window": 20})
    with pytest.raises(ValueError):
        context.get(scope, (wrong,))


@pytest.mark.parametrize("profile", ["LEGACY_FEATURE_AD880AF", "SUPPLIED_LEGACY_FEATURE_AD880AF"])
def test_strict_material_request_rejects_legacy_and_supplied(profile):
    result = score(analysis_for(feature_version=profile))
    assert result.quality is None
    assert "PROFILE_UNSUPPORTED" in result.reasons


def test_quality_requires_exact_strict_request_identity():
    analysis = analysis_for()
    for request in (
        (),
        (RuleRequest("chart.features.strict", "WRONG", {}, ("instrument",), "SESSION_V1"),),
        (replace(rule_request("chart.features.strict"), parameters={"other": 1}),),
    ):
        result = score(replace(analysis, requested_rules=request))
        assert result.quality is None
        assert "STRICT_FEATURE_REQUEST_REQUIRED" in result.reasons


def test_missing_as_of_does_not_silently_score_prior_session():
    frame = bars(list(range(100, 352)))
    scope = scope_for(frame)
    from datetime import timedelta

    from src.tools.technical.chart_analysis.models import CalculationScope, SeriesInput

    scope = CalculationScope(
        SeriesInput(
            replace(scope.primary.manifest, as_of=scope.primary.manifest.as_of + timedelta(days=1)),
            frame,
        ),
        {},
    )
    result = score(AnalysisRequestContext().get(scope, (rule_request("chart.features.strict"),)))
    assert result.quality is None
    assert "INPUT_MISSING" in result.reasons


@pytest.mark.parametrize("difference,want", [(0, 50), (4, 100), (-4, 0)])
def test_distance_normalization_exact_center_and_two_k_atr(difference, want):
    analysis = with_features(analysis_for(), ATR=2, Close=100 + difference, SMA_50=100)
    result = score(analysis)
    assert result.diagnostics["components"]["trend.close_sma50"] == want


def test_four_axes_follow_appendix_without_rounding_or_redistribution():
    analysis = with_features(
        analysis_for(),
        ATR=4,
        Close=102,
        SMA_50=100,
        SMA_150=99,
        SMA_200=98,
        SMA_200_Lag20=97,
        Low_20_New=96,
        Low_20_Prior=95,
        High_20_New=108,
        High_20_Prior=106,
        Close_Lag5=101,
        Close_Lag20=100,
        Close_Lag60=99,
        Up_Volume_20=60,
        Down_Volume_20=40,
    )
    result = score(analysis)
    trend = 0.30 * 62.5 + 0.45 * (56.25 + 56.25 + 62.5) / 3 + 0.25 * 56.25
    structure = 0.40 * 56.25 + 0.40 * 62.5 + 0.20 * 50
    momentum = sum(
        w * (50 + 12.5 * log(102 / old) / ((4 / 102) * sqrt(n)))
        for w, n, old in ((0.2, 5, 101), (0.5, 20, 100), (0.3, 60, 99))
    )
    assert result.axes == pytest.approx(
        {"trend": trend, "structure": structure, "momentum": momentum, "participation": 60},
        abs=1e-10,
    )
    assert result.quality == pytest.approx(
        0.30 * trend + 0.25 * structure + 0.30 * momentum + 0.15 * 60, abs=1e-10
    )
    assert sum(result.contributions.values()) == pytest.approx(result.quality, abs=1e-10)


@pytest.mark.parametrize(
    "count,calculated,published",
    [(219, False, False), (220, True, False), (251, True, False), (252, True, True)],
)
def test_219_220_251_252_calculation_and_publication_are_separate(count, calculated, published):
    result = score(analysis_for(bars(list(range(100, 100 + count)))))
    assert (result.axes["trend"] is not None) is calculated
    assert (result.diagnostics["calculated_quality"] is not None) is calculated
    assert (result.quality is not None) is published
    assert ("HISTORY_SHORT" in result.reasons) is (not calculated)
    assert ("POLICY_HISTORY_SHORT" in result.reasons) is (not published)
    assert result.axes["structure"] is not None


@pytest.mark.parametrize(
    "feature,value,reason",
    [
        ("ATR", 0, "NONPOSITIVE_ATR"),
        ("ATR", -1, "NONPOSITIVE_ATR"),
        ("Close", 0, "NONPOSITIVE_PRICE"),
        ("Close", float("nan"), "INPUT_MISSING"),
        ("SMA_50", None, "INPUT_MISSING"),
    ],
)
def test_invalid_normalization_dependencies_have_explicit_null_reasons(feature, value, reason):
    result = score(with_features(analysis_for(), **{feature: value}))
    assert result.quality is None
    assert reason in result.reasons
    assert result.axes["participation"] is not None


def test_flat_structure_range_is_null_even_with_positive_recursive_atr():
    result = score(with_features(analysis_for(), High_20_New=100, Low_20_New=100))
    assert result.axes["structure"] is None
    assert result.quality is None
    assert "ZERO_PRICE_RANGE" in result.reasons


@pytest.mark.parametrize("kind", ["missing", "provisional", "incomplete"])
def test_publication_preserves_available_diagnostics_but_rejects_incomplete_final_history(kind):
    frame = bars(100 + np.arange(252) * 0.1 + np.sin(np.arange(252)))
    kwargs = {}
    if kind == "missing":
        frame.loc[frame.index[10], "Volume"] = np.nan
    elif kind == "provisional":
        kwargs["finality"] = {
            day.date(): "PROVISIONAL" if day == frame.index[-1] else "FINAL" for day in frame.index
        }
    else:
        kwargs["coverage"] = {"reached_start": False}
    result = score(analysis_for(frame, **kwargs))
    assert result.quality is None
    assert "INCOMPLETE_PREFIX" in result.reasons
    assert result.diagnostics["features"]["Close"]["value"] is not None
    if kind == "provisional":
        assert "PROVISIONAL_PREVIEW" in result.reasons


def test_quality_consumes_only_analysis_features_after_calculation(monkeypatch):
    analysis = analysis_for()
    expected = score(analysis)
    from src.tools.technical.chart_analysis import features

    monkeypatch.setattr(
        features, "calculate_features", lambda *_: pytest.fail("Quality recomputed features")
    )
    assert score(analysis) == expected


def test_unrelated_unavailable_feature_in_request_union_does_not_block_quality():
    analysis = analysis_for()
    before = score(analysis)
    after = score(
        with_features(
            analysis, Unrelated_Feature=FeatureValue(None, "UNAVAILABLE", ("OTHER_RULE_MISSING",))
        )
    )
    assert after.quality == before.quality
    assert after.axes == before.axes
    assert after.reasons == before.reasons


def test_required_feature_null_retains_its_specific_reason():
    result = score(
        with_features(
            analysis_for(), SMA_50=FeatureValue(None, "UNAVAILABLE", ("MISSING_SESSION",))
        )
    )
    assert result.axes["trend"] is None and result.quality is None
    assert "MISSING_SESSION" in result.reasons
    assert result.axes["structure"] is not None


@pytest.mark.parametrize("difference,want", [(0, 50), (8, 100), (-8, 0)])
def test_distance_k2_uses_twice_the_atr_unit(difference, want):
    result = score(with_features(analysis_for(), ATR=2, Close=100 + difference, SMA_200=100))
    assert result.diagnostics["components"]["trend.close_sma200"] == want


@pytest.mark.parametrize("previous,want", [(1, 100), (1e8, 0)])
def test_momentum_return_clips_at_zero_and_one_hundred(previous, want):
    result = score(with_features(analysis_for(), Close_Lag5=previous))
    assert result.diagnostics["components"]["momentum.return_5"] == want


def test_material_request_reuses_strict_numerical_cache_in_new_request_union(monkeypatch):
    from src.tools.technical.chart_analysis import features

    original = features.calculate_features
    calls = []

    def calculate(scope):
        calls.append(scope.primary.manifest.input_hash)
        return original(scope)

    monkeypatch.setattr(features, "calculate_features", calculate)
    scope = scope_for(bars(list(range(100, 352))))
    context = AnalysisRequestContext()
    request = rule_request("chart.features.strict")
    first = context.get(scope, (request,))
    union = context.get(scope, (request, rule_request("chart.rsi.wilder")))
    assert union.analysis_id != first.analysis_id
    assert union.features == first.features
    assert len(calls) == 1
