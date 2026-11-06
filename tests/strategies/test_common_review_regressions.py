"""Independent review counterexamples: union identity and preserved provenance."""

from dataclasses import replace

import pytest

from src.strategies.models import BarFinality
from src.strategies.observations.common import observation_anchors, observation_rules
from src.strategies.observations.detectors import evaluate_observations
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.swing_w150.common import (
    feature_scope,
    frame_scope,
    raw_rules,
    swing_rules,
)
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.strategies.swing_w150.signals import detect_swing
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.features import LEGACY_VERSION
from src.tools.technical.chart_analysis.registry import rule_request
from tests.strategies.swing_w150.conftest import SignalFactory
from tests.strategies.swing_w150.test_features import _raw_ohlcv
from tests.strategies.test_observations import features


def identity(request):
    return request.rule_id, request.rule_version, request.parameter_id


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("multiple,wanted", [(1.4, ["TREND_BREAKOUT_ENTRY"]), (10, [])])
def test_swing_parameter_union_consumes_and_selects_only_exact_requests(reverse, multiple, wanted):
    default = SwingW150Parameters()
    custom = replace(
        default, parameter_set_version="CUSTOM_VOLUME_10", trend_breakout_volume_multiple=10
    )
    selected = default if multiple == 1.4 else custom
    f = SignalFactory().make([{"Close": 150, "High": 151, "Volume": 200}])
    requests = (*swing_rules(default), *swing_rules(custom))
    analysis = AnalysisRequestContext().get(feature_scope("TEST", f), requests)
    if reverse:
        analysis = replace(analysis, items=tuple(reversed(analysis.items)))
    result = detect_swing("TEST", f, selected, common_analysis=analysis)
    assert [signal.code for signal in result.current_signals] == wanted
    by_id = {item.id: item for item in analysis.items}
    selected_keys = {
        identity(request)
        for request in swing_rules(selected)
        if request.rule_id not in ("chart.pivot.span3", "chart.structure_breakdown.swing")
    }
    for selection in result.fact_selections:
        item = by_id[selection.ref.item_id]
        assert selection.selected == (
            (item.rule_id, item.rule_version, item.parameter_id) in selected_keys
        )


@pytest.mark.parametrize("lookback", [7, 21])
def test_raw_feature_union_reads_the_callers_exact_frame_variant(lookback):
    raw = _raw_ohlcv()
    default = SwingW150Parameters()
    custom = replace(default, parameter_set_version="CUSTOM_SLOPE_7", direction_lookback_bars=7)
    selected = custom if lookback == 7 else default
    scope = frame_scope("TEST", raw, feature_version=LEGACY_VERSION)
    analysis = AnalysisRequestContext().get(scope, (*raw_rules(default), *raw_rules(custom)))
    # Put the other valid variant first: transport order must not select a policy.
    target = raw_rules(selected)[0]
    analysis = replace(
        analysis,
        items=tuple(
            sorted(analysis.items, key=lambda item: item.parameter_id == target.parameter_id)
        ),
    )
    result = build_swing_features(raw, selected, common_analysis=analysis)
    assert f"SMA_50_Slope_{lookback}" in result.frame
    if lookback == 21:
        assert "SMA_50_Slope_7" not in result.frame


def test_v1_build_features_ignores_another_valid_s01_variant():
    from src.strategies.swing_w150.rules import build_features

    default = SwingW150Parameters()
    custom = replace(
        default, parameter_set_version="CUSTOM_VOLUME_10", trend_breakout_volume_multiple=10
    )
    f = SignalFactory().make([{"Close": 150, "High": 151, "Volume": 200}])
    frame = f.frame.copy()
    frame["Low_20"] = 100
    f = replace(f, frame=frame)
    analysis = AnalysisRequestContext().get(
        feature_scope("TEST", f),
        (*swing_rules(default, replay=True), *swing_rules(custom, replay=True)),
    )
    target = swing_rules(default, replay=True)[0]
    analysis = replace(
        analysis,
        items=tuple(
            sorted(analysis.items, key=lambda item: item.parameter_id == target.parameter_id)
        ),
    )
    assert build_features(frame, common_analysis=analysis).s_trigger[-1]


def test_observations_ignore_unrelated_rules_and_other_thresholds():
    params = ObservationParameters(contraction_ratio=0.7)
    f = SignalFactory().make([{"Close": 150, "High": 151, "Volume": 200}])
    frame = f.frame.copy()
    frame["Contraction_Context"] = True
    frame["Volume_Contraction_Ratio"] = 0.8
    f = replace(f, frame=frame)
    other_threshold = rule_request(
        "OBSERVATION_V1",
        {"code": "VOLUME_CONTRACTION", "threshold": 0.9, "frame_policy": "SUPPLIED_AS_IS"},
    )
    analysis = AnalysisRequestContext().get(
        feature_scope("TEST", f),
        (*observation_rules(params), *swing_rules(SwingW150Parameters()), other_threshold),
        observation_anchors(f, ()),
    )
    history = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=params, common_analysis=analysis
    )
    assert history == []
    assert history.fact_selections
    assert all(not selection.selected for selection in history.fact_selections)


def test_v1_prepared_facts_preserve_every_coverage_field_and_scope_metadata():
    from src.strategies.swing_w150.adapter import SwingW150Strategy
    from tests.strategies.test_common_chart_parity import _bundle

    bundle = _bundle(_raw_ohlcv(), listing=True, provisional=True)
    result = SwingW150Strategy().evaluate(bundle)
    assert len(result.common_analyses) == 2
    raw, prepared = result.common_analyses
    assert dict(raw.manifest.coverage) == bundle.instrument.coverage.model_dump(mode="python")
    assert prepared.manifest.coverage == raw.manifest.coverage
    assert prepared.manifest.finality == raw.manifest.finality
    assert prepared.manifest.input_profile == raw.manifest.input_profile == bundle.profile_version
    assert prepared.manifest.calendar_version == raw.manifest.calendar_version


@pytest.mark.parametrize("supplied_as_is,wanted", [(False, 0), (True, 1)])
def test_nonfinal_preview_filter_is_only_a_selected_compatibility_policy(supplied_as_is, wanted):
    f = features(
        [
            {"Contraction_Context": True, "Volume_Contraction_Ratio": ratio}
            for ratio in (0.8, 0.6, 0.6)
        ]
    )
    frame = f.frame.copy()
    frame["Open"] = frame["Close"] = frame["Low"] = 100
    frame["High"] = 101
    frame["Volume"] = 10
    f = replace(
        f,
        frame=frame,
        finalities=(BarFinality.FINAL, BarFinality.PROVISIONAL, BarFinality.PROVISIONAL),
    )
    params = {"code": "VOLUME_CONTRACTION", "threshold": 0.7}
    if supplied_as_is:
        params["frame_policy"] = "SUPPLIED_AS_IS"
    request = rule_request("OBSERVATION_V1", params)
    analysis = AnalysisRequestContext().get(feature_scope("TEST", f), (request,))
    assert len([item for item in analysis.items if item.kind == "EPISODE"]) == wanted


def test_explicit_v2_consumes_only_the_final_mask_pivot_request():
    from scripts.research_trading_observations import explicit_research_parameters

    params = explicit_research_parameters()
    highs = [1, 2, 3, 6, 3, 2, 1, 2, 3, 8, 3, 2, 1]
    f = SignalFactory().make([{"High": high, "Low": 0} for high in highs])
    frame = f.frame.copy()
    frame["History_Bars"] = range(1, len(frame) + 1)
    frame["Price_Breakout_Event"] = False
    finalities = list(f.finalities)
    finalities[253] = BarFinality.PROVISIONAL
    f = replace(f, frame=frame, finalities=tuple(finalities))
    context = AnalysisRequestContext()
    expected = context.get(feature_scope("TEST", f), swing_rules(params))
    union = context.get(
        feature_scope("TEST", f),
        (*swing_rules(params), rule_request("chart.pivot.span3", {"final_mask": False})),
    )
    actual = detect_swing("TEST", f, params, common_analysis=union)
    assert (
        actual.model_dump()
        == detect_swing("TEST", f, params, common_analysis=expected).model_dump()
    )
    required = rule_request("chart.pivot.span3", {"final_mask": True})
    by_id = {item.id: item for item in union.items}
    for selection in actual.fact_selections:
        item = by_id[selection.ref.item_id]
        if item.rule_id == "chart.pivot.span3":
            assert selection.selected == (item.parameter_id == required.parameter_id)
