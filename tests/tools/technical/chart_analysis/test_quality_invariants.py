"""Unit changes and delta decomposition preserve unrounded numerical contracts."""

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from tests.tools.technical.chart_analysis.test_features import bars
from tests.tools.technical.chart_analysis.test_quality import (
    analysis_for,
    api,
    score,
    with_features,
)


@pytest.mark.parametrize("price_scale,volume_scale", [(0.1, 100), (7.3, 0.01), (1000, 13)])
def test_independent_positive_price_and_volume_units_preserve_quality(price_scale, volume_scale):
    frame = bars(100 + np.arange(252) * 0.05 + np.sin(np.arange(252)))
    frame["Volume"] = 100 + np.arange(252) % 13
    base = score(analysis_for(frame))
    frame[["Open", "High", "Low", "Close"]] *= price_scale
    frame["Volume"] *= volume_scale
    result = score(analysis_for(frame))
    assert result.axes == pytest.approx(base.axes, abs=1e-10)
    assert result.quality == pytest.approx(base.quality, abs=1e-10)
    assert result.reasons == base.reasons
    assert result.diagnostics["participation"]["max_share"] == pytest.approx(
        base.diagnostics["participation"]["max_share"], abs=1e-10
    )


def test_delta_axis_and_subcomponent_contributions_sum_to_quality_change():
    analysis = analysis_for()
    before = score(analysis)
    after = score(
        with_features(analysis, Close=analysis.features["Close"].value + 0.12345, Up_Volume_20=134)
    )
    delta = api().explain_delta(before, after)
    assert delta.quality == pytest.approx(after.quality - before.quality, abs=1e-10)
    assert sum(delta.axis_contributions.values()) == pytest.approx(delta.quality, abs=1e-10)
    assert sum(delta.subfeature_contributions.values()) == pytest.approx(delta.quality, abs=1e-10)
    assert list(delta.axis_contributions) == ["trend", "structure", "momentum", "participation"]
    for key, weight in (
        ("trend", 0.3),
        ("structure", 0.25),
        ("momentum", 0.3),
        ("participation", 0.15),
    ):
        assert delta.axis_contributions[key] == weight * (after.axes[key] - before.axes[key])
    assert delta.reasons == ()


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("score_version", "OTHER", "SCORE_VERSION_MISMATCH"),
        ("parameter_id", "OTHER", "PARAMETER_MISMATCH"),
    ],
)
def test_delta_rejects_score_or_parameter_mismatch(field, value, reason):
    before = score()
    delta = api().explain_delta(before, replace(before, **{field: value}))
    assert delta.quality is None and reason in delta.reasons
    assert all(value is None for value in delta.axis_contributions.values())
    assert all(value is None for value in delta.subfeature_contributions.values())


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("feature_version", "OTHER", "FEATURE_VERSION_MISMATCH"),
        ("input_profile", "OTHER", "INPUT_PROFILE_MISMATCH"),
        ("adjustment_policy", "OTHER", "ADJUSTMENT_POLICY_MISMATCH"),
        ("ticker", "OTHER", "INSTRUMENT_MISMATCH"),
        ("exchange", "OTHER", "INSTRUMENT_MISMATCH"),
        ("calendar_version", "OTHER", "CALENDAR_VERSION_MISMATCH"),
    ],
)
def test_delta_rejects_incompatible_input_identity(field, value, reason):
    before = score()
    after = replace(before, manifest=replace(before.manifest, **{field: value}))
    delta = api().explain_delta(before, after)
    assert delta.quality is None and reason in delta.reasons


@pytest.mark.parametrize("null_before", [False, True])
def test_delta_requires_both_published_endpoints_and_preserves_reason(null_before):
    ready = score()
    unavailable = score(with_features(analysis_for(), ATR=0))
    before, after = (unavailable, ready) if null_before else (ready, unavailable)
    delta = api().explain_delta(before, after)
    assert delta.quality is None
    assert "QUALITY_UNAVAILABLE" in delta.reasons
    assert "NONPOSITIVE_ATR" in delta.reasons


def test_score_parameter_payload_and_results_are_immutable_and_fingerprinted():
    parameters = api().QualityParameters()
    result = api().score_quality(analysis_for(), parameters=parameters)
    assert result.parameter_id == parameters.parameter_id
    assert result.score_version == "CHART_SCORE_V1"
    assert result.diagnostics["parameters"]["publication_min_final_bars"] == 252
    assert result.diagnostics["parameters"]["directional_min_samples"] == 5
    assert result.diagnostics["parameters"]["concentration_threshold"] == 0.5
    with pytest.raises((FrozenInstanceError, AttributeError)):
        parameters.publication_min_final_bars = 220
    with pytest.raises(TypeError):
        result.axes["trend"] = 0
    with pytest.raises(TypeError):
        result.diagnostics["parameters"]["publication_min_final_bars"] = 1


def test_delta_accepts_date_specific_origins_from_one_raw_calendar():
    from datetime import date

    import pandas as pd

    from src.providers.price_history_range import HistoryFinality, RangeCoverage, RawHistory
    from src.tools.technical.chart_analysis.input import prepare_history
    from src.tools.technical.chart_analysis.models import (
        CalculationScope,
        InputManifest,
        SeriesInput,
        plain,
    )
    from src.tools.technical.chart_analysis.registry import rule_request
    from src.tools.technical.chart_analysis.service import AnalysisRequestContext

    class BusinessDayCalendar:
        version = "TEST_BUSINESS_DAYS_V1"
        timezone = "America/New_York"

        def sessions(self, start, end):
            return tuple(pd.bdate_range(start, end).date)

    index = pd.bdate_range("2024-10-21", "2026-10-22")
    frame = bars(100 + np.arange(len(index)) * 0.01 + np.sin(np.arange(len(index))))
    frame.index = index
    source = RawHistory(
        frame,
        "fixture",
        "SYNTHETIC_ADJUSTED",
        None,
        {day.date(): HistoryFinality.FINAL for day in index},
        RangeCoverage(index[0].date(), index[-1].date(), True),
    )
    context = AnalysisRequestContext()
    endpoints = []
    for day in (date(2026, 10, 21), date(2026, 10, 22)):
        prepared = prepare_history(source, as_of=day, calendar=BusinessDayCalendar())
        manifest = InputManifest(
            "TEST",
            "XNYS",
            prepared.session,
            prepared.input_start.isoformat(),
            prepared.input_origin_policy,
            "CHART_FEATURE_V1",
            "",
            prepared.adjustment_policy,
            prepared.calendar_version,
            prepared.finality,
            plain(prepared.coverage),
        )
        scope = CalculationScope(SeriesInput(manifest, prepared.frame), {})
        endpoints.append(score(context.get(scope, (rule_request("chart.features.strict"),))))
    before, after = endpoints
    assert before.manifest.origin == "2024-10-21"
    assert after.manifest.origin == "2024-10-22"
    assert before.diagnostics["features"]["History_Bars"]["value"] == 523
    assert after.diagnostics["features"]["History_Bars"]["value"] == 523
    assert before.quality is not None and after.quality is not None
    assert before.reasons == after.reasons == ()
    assert before.manifest.finality[before.as_of] == "FINAL"
    assert after.manifest.finality[after.as_of] == "FINAL"
    delta = api().explain_delta(before, after)
    assert sum(delta.subfeature_contributions.values()) == pytest.approx(
        after.quality - before.quality, abs=1e-10
    )
    assert delta.quality == pytest.approx(after.quality - before.quality, abs=1e-10)
    assert sum(delta.axis_contributions.values()) == pytest.approx(delta.quality, abs=1e-10)
    assert delta.reasons == ()
