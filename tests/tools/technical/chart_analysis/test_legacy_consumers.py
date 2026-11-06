"""Consumer parity and scope/bypass contracts for explicitly injected chart facts."""

from dataclasses import replace
from importlib import import_module

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.registry import rule_request
from src.tools.technical.context import build_market_context
from src.tools.technical.indicators import IndicatorCalculator
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


FAMILIES = (
    "chart.stage2.minervini",
    "chart.velocity.legacy",
    "chart.crsi.legacy",
    "chart.supertrend.legacy",
    "chart.vcp.legacy",
    "chart.legacy.patterns_extra",
    "chart.legacy.volume_extra",
    "chart.pocket_pivot.down_candle",
    "chart.power_gap",
    "legacy.confluence",
    "legacy.divergence",
    "chart.context.breakdown",
    "chart.close_breakout.nanmax",
    "chart.legacy.state_windows",
)


def analysis_for(frame, families=FAMILIES, *, ticker=None):
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    if ticker is not None:
        from src.tools.technical.chart_analysis.models import CalculationScope, SeriesInput

        scope = CalculationScope(
            SeriesInput(replace(scope.primary.manifest, ticker=ticker), frame), {}
        )
    from src.tools.technical.trigger_registry import TRIGGER_RULES

    requests = tuple(rule_request(rule) for rule in families) + tuple(
        rule_request(rule.code, {"frame_policy": "SUPPLIED_AS_IS"}) for rule in TRIGGER_RULES
    )
    return AnalysisRequestContext().get(scope, requests)


def supplied_case(case):
    frame = bars([100.0] * 230)
    for column, value in {
        "SMA_20": 100.0,
        "SMA_50": 100.0,
        "SMA_150": 95.0,
        "SMA_200": 90.0,
        "High_52w": 120.0,
        "Low_52w": 60.0,
        "Vol_SMA_20": 200.0,
        "cRSI": 50.0,
        "cRSI_HighBand": 60.0,
        "cRSI_LowBand": 40.0,
        "RSI": 50.0,
        "SuperTrend_Dir": 1.0,
        "SuperTrend_Up": 95.0,
    }.items():
        frame[column] = value
    frame["ATR"] = [10.0] * 226 + [7.996] * 4
    frame.iloc[-1, frame.columns.get_loc("Volume")] = 259.0 if case == "ratio" else 259.01
    if case == "nan":
        frame.iloc[-2, frame.columns.get_loc("SuperTrend_Dir")] = np.nan
        frame.iloc[-7, frame.columns.get_loc("RSI")] = np.nan
        frame.iloc[-6, frame.columns.get_loc("High")] = np.nan
    return frame


@pytest.mark.parametrize("case", ["vcp", "ratio", "equality", "nan", "short"])
@pytest.mark.parametrize(
    "component",
    ["minervini", "velocity", "crsi", "supertrend", "patterns", "volume", "risk", "divergence"],
)
def test_legacy_component_full_payload_parity(case, component):
    frame = supplied_case(case)
    if case == "short":
        frame = frame.iloc[:10]
    function = getattr(
        import_module(f"src.tools.technical.components.{component}"), f"analyze_{component}"
    )
    old = function(frame).model_dump()
    result = function(frame, common_analysis=analysis_for(frame))
    assert result.model_dump() == old


@pytest.mark.parametrize("case", ["vcp", "ratio", "equality", "nan"])
def test_context_exact_raw_rounding_and_equality(case):
    frame = supplied_case(case)
    result = build_market_context(frame, common_analysis=analysis_for(frame))
    assert result == build_market_context(frame)
    assert result.close_above_sma50 is False
    assert result.volume_ratio_20d == (1.29 if case == "ratio" else 1.3)


@pytest.mark.parametrize("mismatch", ["date", "content"])
def test_reject_analysis_from_another_evaluation_scope(mismatch):
    frame = supplied_case("vcp")
    analysis = analysis_for(frame)
    if mismatch == "date":
        analysis = replace(
            analysis, manifest=replace(analysis.manifest, as_of=pd.Timestamp("2024-01-01").date())
        )
    else:
        frame.iloc[-1, frame.columns.get_loc("Close")] += 1
    with pytest.raises(ValueError, match="scope"):
        build_market_context(frame, common_analysis=analysis)


def test_common_components_bypass_old_numerical_detector_bodies(monkeypatch):
    frame = IndicatorCalculator().calculate(
        pd.read_csv("tests/fixtures/chart_analysis/seed_path.csv", index_col=0, parse_dates=True)
    )
    analysis = analysis_for(frame)
    expected = {}
    for name in ("velocity", "patterns", "volume", "divergence"):
        module = import_module(f"src.tools.technical.components.{name}")
        expected[name] = getattr(module, f"analyze_{name}")(frame).model_dump()

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy numerical detector called")

    for name, methods in {
        "velocity": ("_linear_slope",),
        "patterns": ("_detect_vcp", "_detect_breakout", "_detect_candlestick_patterns"),
        "volume": ("_detect_pocket_pivot", "_detect_tennis_ball_egg", "_detect_power_gap_up"),
        "divergence": (
            "argrelextrema",
            "_detect_bearish_divergence",
            "_detect_bullish_divergence",
            "_detect_macd_divergence",
            "_detect_crsi_divergence",
        ),
    }.items():
        module = import_module(f"src.tools.technical.components.{name}")
        for method in methods:
            monkeypatch.setattr(module, method, forbidden)
        assert (
            getattr(module, f"analyze_{name}")(frame, common_analysis=analysis).model_dump()
            == expected[name]
        )


@pytest.mark.parametrize("case", ["vcp", "nan", "short"])
def test_common_state_windows_keep_raw_nan_and_missing_semantics(case):
    from src.tools.technical.bottoming import _detect_higher_low, _detect_volume_dry
    from src.tools.technical.chart_analysis.legacy_facts import legacy_fact_values_from_frame
    from src.tools.technical.shadow_v2 import (
        _buy_flip_age,
        _close_below_sma20_streak,
        _established_weakness,
    )

    frame = supplied_case(case)
    frame["Low"] = np.r_[np.full(200, 90.0), np.full(30, 95.0)]
    frame["Volume"] = np.r_[np.full(225, 100.0), np.full(5, 50.0)]
    if case == "nan":
        frame.iloc[-3, frame.columns.get_loc("Low")] = np.nan
        frame.iloc[-2, frame.columns.get_loc("Volume")] = np.nan
    if case == "short":
        frame = frame.iloc[:10]
    result = legacy_fact_values_from_frame(frame, family="chart.legacy.state_windows")
    assert (result["st_up"], result["buy_flip_age"]) == _buy_flip_age(frame)
    assert result["below_sma20_streak"] == _close_below_sma20_streak(frame, 2)
    assert (result["below_sma50_count"] >= 8) == _established_weakness(frame)
    assert bool(
        result["recent_low"] is not None
        and result["prior_low"] is not None
        and result["recent_low"] > result["prior_low"]
    ) == _detect_higher_low(frame)
    assert bool(
        result["recent_volume_mean"] is not None
        and result["prior_volume_mean"] is not None
        and result["prior_volume_mean"] > 0
        and result["recent_volume_mean"] < 0.85 * result["prior_volume_mean"]
    ) == _detect_volume_dry(frame)


def test_common_directional_windows_return_raw_values_before_consumer_enum_and_round():
    from src.tools.technical.chart_analysis.legacy_facts import legacy_fact_values_from_frame

    frame = bars([100.0] * 25)
    frame["SMA_20"] = np.arange(100.0, 125.0)
    frame["cRSI"] = np.arange(25.0)
    frame["Volume"] = np.arange(10.0, 35.0)
    result = legacy_fact_values_from_frame(frame, family="chart.legacy.state_windows")[
        "directional"
    ]
    assert result["SMA_20"]["value"] == 124.0
    assert result["SMA_20"]["delta"] == 1.0
    assert result["SMA_20"]["slope"] == pytest.approx(21 / 103 * 100)
    assert result["SMA_20"]["prior_slope"] == pytest.approx(21 / 102 * 100)
    assert result["cRSI"]["slope"] == 5.0
    assert result["Volume"]["slope"] == pytest.approx(5 / 29 * 100)


def test_aprime_and_bottoming_common_path_bypass_old_numerical_helpers(monkeypatch):
    import src.tools.technical.bottoming as bottoming
    import src.tools.technical.shadow_v2 as shadow
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("nan")
    legacy = TechnicalScorer().score(frame, include_history=False)
    analysis = analysis_for(frame)
    context = build_market_context(frame)
    expected = shadow.compute_shadow_v2(frame, legacy.components, context)
    expected_bottoming = bottoming.detect_bottoming_structure(frame, legacy.components, context)

    def forbidden(*args, **kwargs):
        raise AssertionError("old A-prime numerical body called")

    for module, methods in (
        (
            shadow,
            (
                "_velocity_state",
                "_crsi_state",
                "_detect_vcp",
                "_fresh_close_breakout",
                "_buy_flip_age",
                "_close_below_sma20_streak",
                "_established_weakness",
                "_detect_higher_low",
                "_detect_volume_dry",
            ),
        ),
        (bottoming, ("_detect_higher_low", "_detect_volume_dry")),
    ):
        for method in methods:
            monkeypatch.setattr(module, method, forbidden)
    assert (
        shadow.compute_shadow_v2(frame, legacy.components, context, common_analysis=analysis)
        == expected
    )
    assert (
        bottoming.detect_bottoming_structure(
            frame, legacy.components, context, common_analysis=analysis
        )
        == expected_bottoming
    )


@pytest.mark.parametrize("component", ["minervini", "risk"])
def test_supplied_missing_feature_columns_keep_original_component_meaning(component):
    frame = supplied_case("vcp").drop(columns=["High_52w", "Low_52w", "Vol_SMA_20"])
    function = getattr(
        import_module(f"src.tools.technical.components.{component}"), f"analyze_{component}"
    )
    assert (
        function(frame, common_analysis=analysis_for(frame)).model_dump()
        == function(frame).model_dump()
    )


def test_supplied_context_does_not_invent_missing_volume_average():
    frame = supplied_case("vcp").drop(columns="Vol_SMA_20")
    assert build_market_context(frame, common_analysis=analysis_for(frame)) == build_market_context(
        frame
    )


def test_scorecard_common_path_bypasses_old_metric_and_trigger_numerics(monkeypatch):
    import src.tools.technical.scorecard as scorecard
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("nan")
    legacy = TechnicalScorer().score(frame, include_history=False)
    analysis = analysis_for(frame, ticker="TEST")
    expected = scorecard.build_scorecard(frame, legacy, ticker="TEST", as_of=frame.index[-1].date())
    original_metric = scorecard._metric

    def forbid_old_metric(*args, **kwargs):
        if kwargs.get("common_values") is None:
            raise AssertionError("old directional window called")
        return original_metric(*args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("old trigger numerical body called")

    monkeypatch.setattr(scorecard, "_metric", forbid_old_metric)
    monkeypatch.setattr(scorecard, "detect_analysis_triggers", forbidden)
    assert (
        scorecard.build_scorecard(
            frame, legacy, ticker="TEST", as_of=frame.index[-1].date(), common_analysis=analysis
        ).model_dump()
        == expected.model_dump()
    )


def test_supplied_trigger_policy_keeps_missing_column_skip_and_display_order():
    from src.tools.technical.scorecard import _triggers_from_common
    from src.tools.technical.trigger_registry import TRIGGER_RULES
    from src.tools.technical.triggers import detect_analysis_triggers

    frame = bars([100.0] * 25)
    frame.iloc[-1, frame.columns.get_loc("High")] = 120.0
    frame.iloc[-1, frame.columns.get_loc("Close")] = 110.0
    # Raw OHLCV lacks rolling references; legacy correctly skips derived triggers.
    rules = tuple(
        rule_request(rule.code, {"frame_policy": "SUPPLIED_AS_IS"}) for rule in TRIGGER_RULES
    )
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    result = AnalysisRequestContext().get(scope, rules)
    assert (
        _triggers_from_common(result)
        == detect_analysis_triggers(frame, as_of=frame.index[-1].date())
        == []
    )


def test_technical_result_retains_resolvable_selected_facts_without_payload_changes():
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("vcp")
    result = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    assert result.common_analyses
    assert result.fact_selections
    analyses = {analysis.analysis_id: analysis for analysis in result.common_analyses}
    for selection in result.fact_selections:
        assert any(
            item.id == selection.ref.item_id for item in analyses[selection.ref.analysis_id].items
        )
    assert "fact_selections" not in result.model_dump()
    assert "common_analyses" not in result.model_dump()


def test_injected_analysis_rejects_different_instrument_at_scorer_boundary():
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("vcp")
    with pytest.raises(ValueError, match="scope"):
        TechnicalScorer().score(
            frame, ticker="OTHER", common_analysis=analysis_for(frame, ticker="TEST")
        )


@pytest.mark.parametrize(
    "component,columns",
    [
        ("velocity", ["SMA_20", "Close"]),
        ("crsi", ["cRSI", "cRSI_HighBand", "cRSI_LowBand"]),
        ("divergence", ["Close", "RSI"]),
        ("supertrend", ["SuperTrend_Dir", "SuperTrend_Up", "Close"]),
    ],
)
def test_direct_supplied_components_require_only_their_own_inputs(component, columns):
    frame = supplied_case("nan")[columns]
    family = {
        "velocity": "chart.velocity.legacy",
        "crsi": "chart.crsi.legacy",
        "divergence": "legacy.divergence",
        "supertrend": "chart.supertrend.legacy",
    }[component]
    common = analysis_for(frame, families=(family,))
    function = getattr(
        import_module(f"src.tools.technical.components.{component}"), f"analyze_{component}"
    )
    assert function(frame, common_analysis=common).model_dump() == function(frame).model_dump()


def test_scorecard_retains_only_consumed_refs_and_excludes_metadata():
    from src.tools.technical.scorecard import build_scorecard
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("vcp")
    analysis = analysis_for(frame, ticker="TEST")
    legacy = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    result = build_scorecard(
        frame, legacy, ticker="TEST", as_of=frame.index[-1].date(), common_analysis=analysis
    )
    assert result.common_analyses == (analysis,)
    assert result.fact_selections
    assert all(
        selection.ref.analysis_id == analysis.analysis_id for selection in result.fact_selections
    )
    assert "common_analyses" not in result.model_dump()
    assert "fact_selections" not in result.model_dump()


@pytest.mark.parametrize(
    "field,value", [("rule_version", "OTHER_VERSION"), ("parameter_id", "wrong-window")]
)
def test_injected_fact_must_match_requested_compatibility_rule(field, value):
    frame = supplied_case("vcp")
    analysis = analysis_for(frame)
    items = tuple(
        replace(item, **{field: value}) if item.rule_id == "chart.context.breakdown" else item
        for item in analysis.items
    )
    with pytest.raises(ValueError, match="contract"):
        build_market_context(frame, common_analysis=replace(analysis, items=items))


@pytest.mark.asyncio
async def test_tool_transports_the_request_context_for_later_consumer_fact_resolution():
    from src.tools.technical.scorer import TechnicalScorer
    from src.tools.technical.tool import TechnicalAnalysisTool

    frame = bars(np.linspace(100, 120, 230))

    class FixtureProvider:
        async def get_price_history(self, ticker, period):
            return frame.copy()

    context = AnalysisRequestContext()
    result = await TechnicalAnalysisTool(FixtureProvider(), TechnicalScorer()).execute(
        "TEST", request_context=context
    )
    assert result.success
    selection = result.data.fact_selections[0]
    assert context.resolve(selection.ref).id == selection.ref.item_id


def test_retained_immutable_analysis_survives_legacy_result_deepcopy():
    from copy import deepcopy

    from src.tools.technical.scorer import TechnicalScorer

    result = TechnicalScorer().score(supplied_case("vcp"), ticker="TEST", include_history=False)
    copied = deepcopy(result)
    assert copied.common_analyses[0] is result.common_analyses[0]
    assert copied.scorecard.common_analyses[0] is result.common_analyses[0]
    copied.components["patterns"]["signals"].append("copy-only")
    assert "copy-only" not in result.components["patterns"]["signals"]
    assert copied.scorecard.model_dump() == result.scorecard.model_dump()
    analysis = copied.common_analyses[0]
    from dataclasses import FrozenInstanceError

    with pytest.raises(TypeError):
        analysis.features["external"] = None
    with pytest.raises(TypeError):
        analysis.items[0].evidence["external"] = None
    with pytest.raises(TypeError):
        analysis.manifest.coverage["complete"] = False
    with pytest.raises(FrozenInstanceError):
        analysis.manifest.ticker = "OTHER"
    with pytest.raises(FrozenInstanceError):
        analysis.requested_rules = ()
    with pytest.raises(TypeError):
        analysis.requested_rules[0].parameters["external"] = None


@pytest.mark.parametrize("mismatch", ["missing", "version", "parameters", "roles", "alignment"])
def test_zero_event_rule_inventory_distinguishes_not_requested_from_no_event(mismatch):
    from src.tools.technical.context import common_analysis_for_frame
    from src.tools.technical.scorecard import build_scorecard
    from src.tools.technical.scorer import TechnicalScorer, technical_rule_requests

    frame = bars([100.0] * 25)
    analysis = common_analysis_for_frame(frame, ticker="TEST", rules=technical_rule_requests())
    assert not any(item.rule_id.startswith("analysis.") for item in analysis.items)
    legacy = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    valid = build_scorecard(
        frame, legacy, ticker="TEST", as_of=frame.index[-1].date(), common_analysis=analysis
    )
    assert valid.triggers == []
    requests = list(technical_rule_requests())
    target = next(i for i, rule in enumerate(requests) if rule.rule_id.startswith("analysis."))
    if mismatch == "missing":
        requests.pop(target)
    else:
        field, value = {
            "version": ("rule_version", "OTHER"),
            "parameters": ("parameters", {"frame_policy": "SUPPLIED_AS_IS", "display_bars": 0}),
            "roles": ("input_roles", ("market",)),
            "alignment": ("alignment_version", "OTHER"),
        }[mismatch]
        requests[target] = replace(requests[target], **{field: value})
    analysis = replace(analysis, requested_rules=tuple(requests))
    with pytest.raises(ValueError, match="request.*contract"):
        build_scorecard(
            frame, legacy, ticker="TEST", as_of=frame.index[-1].date(), common_analysis=analysis
        )


def test_scorecard_selects_its_trigger_variant_from_a_valid_request_union():
    from src.tools.technical.context import common_analysis_for_frame
    from src.tools.technical.scorecard import build_scorecard
    from src.tools.technical.scorer import TechnicalScorer, technical_rule_requests

    frame = bars([100.0] * 22 + [110.0])
    frame["High_20_Prev"] = frame["High"].rolling(20).max().shift(1)
    requests = technical_rule_requests() + (rule_request("analysis.price.high_20_breakout"),)
    analysis = common_analysis_for_frame(frame, ticker="TEST", rules=requests)
    legacy = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    expected = build_scorecard(frame, legacy, ticker="TEST", as_of=frame.index[-1].date())
    actual = build_scorecard(
        frame, legacy, ticker="TEST", as_of=frame.index[-1].date(), common_analysis=analysis
    )
    assert actual.model_dump() == expected.model_dump()
    assert any(
        not selection.selected and selection.reason_code == "SCORECARD_TRIGGER_VARIANT_NOT_SELECTED"
        for selection in actual.fact_selections
    )


def _consumer_selection(result, consumer, rule_id):
    items = {item.id: item for analysis in result.common_analyses for item in analysis.items}
    return next(
        selection
        for selection in result.fact_selections
        if selection.reason_code.startswith(consumer + "_")
        and items[selection.ref.item_id].rule_id == rule_id
    )


@pytest.mark.parametrize(
    "case,component,rule,reason",
    [
        (
            "volume_missing",
            "volume",
            "chart.pocket_pivot.down_candle",
            "LEGACY_VOLUME_MISSING_VOL_SMA_20",
        ),
        (
            "volume_one_bar",
            "volume",
            "chart.pocket_pivot.down_candle",
            "LEGACY_VOLUME_HISTORY_SHORT",
        ),
        (
            "volume_zero",
            "volume",
            "chart.pocket_pivot.down_candle",
            "LEGACY_VOLUME_VALUES_UNAVAILABLE",
        ),
        (
            "volume_nan",
            "volume",
            "chart.pocket_pivot.down_candle",
            "LEGACY_VOLUME_VALUES_UNAVAILABLE",
        ),
        (
            "patterns_two_bars",
            "patterns",
            "chart.legacy.patterns_extra",
            "LEGACY_PATTERNS_HISTORY_SHORT",
        ),
        (
            "minervini_short",
            "minervini",
            "chart.stage2.minervini",
            "LEGACY_MINERVINI_HISTORY_SHORT",
        ),
        (
            "velocity_missing",
            "velocity",
            "chart.velocity.legacy",
            "LEGACY_VELOCITY_INPUT_UNAVAILABLE",
        ),
        ("crsi_one_bar", "crsi", "chart.crsi.legacy", "LEGACY_CRSI_HISTORY_SHORT"),
        (
            "supertrend_one_bar",
            "supertrend",
            "chart.supertrend.legacy",
            "LEGACY_SUPERTREND_HISTORY_SHORT",
        ),
        ("divergence_short", "divergence", "legacy.divergence", "LEGACY_DIVERGENCE_HISTORY_SHORT"),
        ("risk_short", "risk", "legacy.confluence", "LEGACY_RISK_HISTORY_SHORT"),
    ],
)
def test_legacy_selection_reports_actual_component_early_return(case, component, rule, reason):
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("vcp")
    if case == "volume_missing":
        frame = frame.drop(columns="Vol_SMA_20")
    elif case == "velocity_missing":
        frame = frame.drop(columns="SMA_20")
    elif case == "volume_zero":
        frame.iloc[-1, frame.columns.get_loc("Vol_SMA_20")] = 0.0
    elif case == "volume_nan":
        frame.iloc[-1, frame.columns.get_loc("Volume")] = np.nan
    else:
        count = {
            "volume_one_bar": 1,
            "patterns_two_bars": 2,
            "minervini_short": 100,
            "crsi_one_bar": 1,
            "supertrend_one_bar": 1,
            "divergence_short": 30,
            "risk_short": 10,
        }[case]
        frame = frame.iloc[:count]
    expected = getattr(
        import_module(f"src.tools.technical.components.{component}"), f"analyze_{component}"
    )(frame)
    result = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    assert result.components[component] == expected.model_dump()
    selection = _consumer_selection(result, "LEGACY", rule)
    assert selection.selected is False
    assert selection.reason_code == reason


@pytest.mark.parametrize(
    "rule,reason",
    [
        ("chart.crsi.legacy", "APRIME_CURRENT_CRSI_FROM_STATE_WINDOWS"),
        ("chart.supertrend.legacy", "APRIME_SUPERTREND_FROM_STATE_WINDOWS"),
        ("chart.legacy.patterns_extra", "APRIME_PATTERN_EVENTS_NOT_USED"),
        ("chart.legacy.volume_extra", "APRIME_VOLUME_COMPONENT_NOT_USED"),
        ("chart.pocket_pivot.down_candle", "APRIME_VOLUME_COMPONENT_NOT_USED"),
        ("chart.power_gap", "APRIME_VOLUME_COMPONENT_NOT_USED"),
        ("legacy.divergence", "APRIME_DIVERGENCE_NOT_USED"),
    ],
)
def test_aprime_rejects_legacy_families_it_does_not_consume(rule, reason):
    from src.tools.technical.scorer import TechnicalScorer

    result = TechnicalScorer().score(supplied_case("vcp"), ticker="TEST", include_history=False)
    selection = _consumer_selection(result, "APRIME", rule)
    assert selection.selected is False
    assert selection.reason_code == reason


@pytest.mark.parametrize("rule", ["chart.velocity.legacy", "chart.close_breakout.nanmax"])
def test_aprime_rejects_unavailable_short_measurements(rule):
    from src.tools.technical.scorer import TechnicalScorer

    result = TechnicalScorer().score(
        supplied_case("vcp").iloc[:10], ticker="TEST", include_history=False
    )
    selection = _consumer_selection(result, "APRIME", rule)
    assert selection.selected is False
    assert selection.reason_code == "APRIME_FACT_HISTORY_SHORT"


def test_aprime_current_crsi_and_derived_component_inputs_have_actual_refs():
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("vcp")
    frame.iloc[-2, frame.columns.get_loc("cRSI")] = np.nan
    frame.iloc[-1, frame.columns.get_loc("cRSI")] = 30.0
    result = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    assert _consumer_selection(result, "LEGACY", "chart.crsi.legacy").selected is False
    assert (
        _consumer_selection(result, "APRIME", "chart.crsi.legacy").reason_code
        == "APRIME_CURRENT_CRSI_FROM_STATE_WINDOWS"
    )
    for rule in ("chart.legacy.state_windows", "chart.stage2.minervini", "legacy.confluence"):
        assert _consumer_selection(result, "APRIME", rule).selected is True
    assert (
        result.shadow_v2["setup_score"] == 20
    )  # cRSI +10, raw VCP +20, flat velocity0, resistance confluence-10


@pytest.mark.parametrize(
    "rule,key",
    [
        ("chart.stage2.minervini", "is_stage2"),
        ("chart.velocity.legacy", "upward"),
        ("chart.pocket_pivot.down_candle", "detected"),
    ],
)
def test_read_false_condition_is_still_a_consumed_legacy_fact(rule, key):
    from src.tools.technical.scorer import TechnicalScorer

    result = TechnicalScorer().score(supplied_case("vcp"), ticker="TEST", include_history=False)
    item = next(item for item in result.common_analyses[0].items if item.rule_id == rule)
    assert item.state == "OBSERVED"
    assert item.evidence[key] is False
    selection = _consumer_selection(result, "LEGACY", rule)
    assert selection.selected is True
    assert selection.reason_code == "LEGACY_CONSUMED"


def test_positive_pocket_pivot_is_consumed_by_legacy_and_not_used_by_aprime():
    from src.tools.technical.scorer import TechnicalScorer

    frame = supplied_case("vcp")
    frame["Open"] = 101.0
    result = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    item = next(
        item
        for item in result.common_analyses[0].items
        if item.rule_id == "chart.pocket_pivot.down_candle"
    )
    assert item.evidence["detected"] is True
    assert "Pocket Pivot (기관 매집)" in result.components["volume"]["signals"]
    assert _consumer_selection(result, "LEGACY", item.rule_id).selected is True
    assert _consumer_selection(result, "APRIME", item.rule_id).selected is False
