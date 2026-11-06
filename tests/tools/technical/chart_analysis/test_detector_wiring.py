"""Common shadows are real owners; public bodies remain direct independent oracles."""

from dataclasses import asdict, replace
from importlib import import_module

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.chart_analysis.models import CalculationScope, SeriesInput
from src.tools.technical.chart_analysis.registry import RULE_REGISTRY, rule_request
from src.tools.technical.chart_analysis.service import AnalysisRequestContext
from src.tools.technical.trigger_registry import TRIGGER_RULES
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


def test_common_pivot_shadow_matches_original_mask_and_every_prefix():
    from src.tools.technical.pivots import confirmed_pivot_events

    common = import_module("src.tools.technical.chart_analysis.pivots")
    high = np.array([11, 12, 13, 18, 13, 12, 11, 12, 13, 18, 13, 12, 11, 12, 13, 19, 13, 12, 11.0])
    low = high - 3
    for end in range(1, len(high) + 1):
        for mask in (None, np.array([i % 5 != 0 for i in range(end)])):
            actual = common.confirmed_pivot_events(high[:end], low[:end], final_mask=mask)
            expected = confirmed_pivot_events(high[:end], low[:end], final_mask=mask)
            assert [asdict(x) for x in actual] == [asdict(x) for x in expected]
            assert all(x.confirmed_index < end for x in actual)
    assert common.confirmed_pivot_events.__module__.endswith("chart_analysis.pivots")


def test_common_trigger_shadow_matches_original_all_event_fields():
    from src.tools.technical.indicators import IndicatorCalculator
    from src.tools.technical.triggers import detect_analysis_triggers

    common = import_module("src.tools.technical.chart_analysis.trigger_events")
    raw = pd.read_csv("tests/fixtures/chart_analysis/seed_path.csv", index_col=0, parse_dates=True)
    frame = IndicatorCalculator().calculate(raw)
    expected = detect_analysis_triggers(frame)
    actual = common.detect_trigger_events(frame)
    assert len(actual) == len(expected) > 0
    for left, right in zip(actual, expected, strict=True):
        for field in asdict(left):
            assert getattr(left, field) == getattr(right, field), field


def test_detect_items_missing_api_is_real_and_pivot_not_known_before_confirmation():
    module = import_module("src.tools.technical.chart_analysis.detectors")
    frame = bars([100] * 7)
    frame["Low"] = [99, 98, 97, 90, 97, 98, 99]
    scope = scope_for(frame)
    items = module.detect_items(scope, (rule_request("chart.pivot.span3"),))
    assert len(items) == 1
    assert items[0].occurred_on == frame.index[3].date()
    assert items[0].confirmed_on == frame.index[6].date()
    assert not module.detect_items(scope_for(frame.iloc[:-1]), (rule_request("chart.pivot.span3"),))


def supplied_scope():
    from src.tools.technical.chart_analysis.legacy_features import calculate_legacy_features

    raw = pd.read_csv("tests/fixtures/chart_analysis/seed_path.csv", index_col=0, parse_dates=True)
    instrument = scope_for(
        calculate_legacy_features(raw), feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF"
    ).primary
    market = SeriesInput(
        replace(instrument.manifest, ticker="INDEX", input_hash=""), instrument.raw
    )
    return CalculationScope(instrument, {"market": market})


@pytest.mark.parametrize("entry", RULE_REGISTRY, ids=lambda x: x.rule_id + str(dict(x.parameters)))
def test_every_registered_variant_executes_real_owner_and_immutable_result(entry):
    """Rejecting or dropping an implemented variant fails this integration contract."""
    from src.tools.technical.chart_analysis.detectors import detect_items

    scope = supplied_scope()
    if entry.rule_version == "CHART_RULE_V1":
        scope = scope_for(scope.primary.raw[["Open", "High", "Low", "Close", "Volume"]])
    items = detect_items(scope, (entry,))
    for item in items:
        assert item.rule_id == entry.rule_id
        assert item.state not in ("UNSUPPORTED", "PROFILE_UNSUPPORTED")
        assert item.evidence
        with pytest.raises(TypeError):
            item.evidence["mutation"] = True
    if not entry.rule_id.startswith("analysis.") and entry.rule_id not in (
        "chart.pivot.span3",
        "OBSERVATION_V1",
        "chart.momentum.deceleration",
        "chart.momentum.reacceleration",
        "chart.anchor.break_reclaim",
    ):
        assert items, f"{entry.rule_id} silently returned no result"

    # Adapter values must equal the reviewed numerical owner, not only exist.
    from src.tools.technical.chart_analysis import legacy_facts
    from src.tools.technical.chart_analysis.evaluators import snapshot
    from src.tools.technical.chart_analysis.models import freeze

    if entry.rule_id in legacy_facts.FRAME_FAMILIES and entry.rule_id not in (
        "feature.window",
        "chart.close_breakout.strict",
        "OBSERVATION_V1",
        "chart.momentum.deceleration",
        "chart.momentum.reacceleration",
    ):
        expected = legacy_facts.legacy_fact_values(scope, family=entry.rule_id)
        for key, value in snapshot(expected).items():
            assert items[0].evidence[key] == freeze(value), key
    elif entry.rule_id == "feature.window":
        expected_frame = legacy_facts.prepare_legacy_frame(scope.primary)
        key = entry.parameters["feature_key"]
        assert items[0].evidence["values"] == snapshot(expected_frame[key])
    elif entry.rule_id == "chart.close_breakout.strict":
        expected = legacy_facts.close_breakout_values(
            scope.primary.raw, lookback=entry.parameters["lookback"]
        )
        for key, value in expected.items():
            assert items[0].evidence[key] == snapshot(value)


def test_request_feature_preparation_shared_across_rules_market_change_does_not_recompute(
    monkeypatch,
):
    module = import_module("src.tools.technical.chart_analysis.evaluators")
    original = module.prepare_legacy_frame
    calls = []

    def counted(series):
        calls.append(series.manifest.input_hash)
        return original(series)

    monkeypatch.setattr(module, "prepare_legacy_frame", counted)
    scope = supplied_scope()
    ctx = AnalysisRequestContext()
    first = ctx.get(scope, (rule_request("feature.window", {"feature_key": "Vol_SMA_5"}),))
    second = ctx.get(
        scope,
        (
            rule_request("feature.window", {"feature_key": "High_20_Prev"}),
            rule_request("feature.window", {"feature_key": "Vol_SMA_5"}),
        ),
    )
    changed_market = SeriesInput(
        replace(scope.related["market"].manifest, origin="other"), scope.related["market"].raw
    )
    third = ctx.get(
        CalculationScope(scope.primary, {"market": changed_market}),
        (rule_request("feature.window", {"feature_key": "Vol_SMA_5"}),),
    )
    assert calls == [scope.primary.manifest.input_hash]
    assert first.items[0] is next(x for x in second.items if x.rule_id == first.items[0].rule_id)
    assert first.items[0] is third.items[0]


def test_actual_backend_metadata_changes_analysis_and_evaluation_keys_preserving_old_refs(
    monkeypatch,
):
    from src.tools.technical.chart_analysis.models import FactRef

    module = import_module("src.tools.technical.chart_analysis.evaluators")
    original = module.provider_identity
    scope = supplied_scope()
    ctx = AnalysisRequestContext()
    rule = rule_request("chart.velocity.legacy")
    first = ctx.get(scope, (rule,))
    ref = FactRef(first.analysis_id, first.items[0].id)
    assert first.items[0].evidence["provider_identity"]["calculation"]["backend"] == "numpy/polyfit"

    def changed(*args):
        return {**original(*args), "test_actual_backend_version": "changed"}

    monkeypatch.setattr(module, "provider_identity", changed)
    second = ctx.get(scope, (rule,))
    assert second.analysis_id != first.analysis_id
    assert second.items[0].evaluation_key != first.items[0].evaluation_key
    assert second.items[0].id == first.items[0].id
    assert ctx.resolve(ref) is first.items[0]


def test_unsupported_profile_is_typed_unavailable_not_false_success():
    result = AnalysisRequestContext().get(
        scope_for(bars([100] * 30)), (rule_request("chart.stage2.minervini"),)
    )
    assert result.items[0].state == "UNAVAILABLE"
    assert result.items[0].evidence["reasons"] == ("PROFILE_UNSUPPORTED",)


@pytest.mark.parametrize(
    "rule,closes,expected",
    [
        ("chart.extension.sma20", [100] * 19 + [113.3], True),
        ("chart.extension.sma20", [100] * 20, False),
        ("chart.rsi.wilder", list(range(100, 115)), True),
        ("chart.rsi.wilder", [100] * 15, False),
    ],
)
def test_strict_catalog_has_actual_positive_and_negative_values(rule, closes, expected):
    item = AnalysisRequestContext().get(scope_for(bars(closes)), (rule_request(rule),)).items[0]
    assert item.evidence["detected"] is expected
    assert item.state == ("DETECTED" if expected else "CLEAR")


def observation_scope(*, provisional=False, **columns):
    count = len(next(iter(columns.values())))
    frame = bars([100.0] * count)
    for key, value in columns.items():
        frame[key] = value
    for key in ("SMA_20", "SMA_50", "SMA_150", "SMA_200"):
        if key not in frame:
            frame[key] = 100.0
    frame["SuperTrend_Dir"] = 1.0
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    if provisional:
        finality = {d.date(): "FINAL" for d in frame.index}
        finality[frame.index[-1].date()] = "PROVISIONAL"
        scope = CalculationScope(
            SeriesInput(replace(scope.primary.manifest, finality=finality), frame), {}
        )
    return scope


def test_observation_pivot_preview_adds_only_new_confirmation_without_changing_final_seed():
    highs = [101, 102, 103, 106, 103, 102, 101, 102, 103, 108, 103, 102, 101]
    scope = observation_scope(provisional=True, High=highs, Low=[99] * len(highs))
    rule = rule_request("OBSERVATION_V1", {"code": "HIGHER_HIGH"})
    items = AnalysisRequestContext().get(scope, (rule,)).items
    assert len(items) == 1
    assert items[0].occurred_on == scope.primary.raw.index[-1].date()
    assert items[0].finality == "PROVISIONAL"


def test_contraction_origin_current_and_final_status_match_original_and_preview_cannot_resolve():
    from src.strategies.models import BarFinality
    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.observations.parameters import ObservationParameters
    from src.strategies.swing_w150.features import SwingFeatureFrame
    from src.tools.technical.scorecard_models import DataStatus

    scope = observation_scope(
        provisional=True,
        Contraction_Context=[True] * 4,
        Volume_Contraction_Ratio=[0.6, 0.6, 0.9, 0.6],
    )
    rule = rule_request("OBSERVATION_V1", {"code": "VOLUME_CONTRACTION", "threshold": 0.7})
    actual = AnalysisRequestContext().get(scope, (rule,)).items
    raw = scope.primary.raw
    old = evaluate_observations(
        "TEST",
        SwingFeatureFrame(
            raw, DataStatus.COMPLETE, (BarFinality.FINAL,) * 3 + (BarFinality.PROVISIONAL,)
        ),
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(contraction_ratio=0.7),
    )
    old = [x for x in old if x.code.value == "VOLUME_CONTRACTION"]
    actual = sorted(actual, key=lambda x: x.occurred_on)
    assert [(x.occurred_on, x.state, x.finality, x.status_as_of) for x in actual] == [
        (x.started_on, x.status.value.upper(), x.finality.value.upper(), x.status_as_of)
        for x in old
    ]
    assert actual[0].evidence["origin"]["Volume_Contraction_Ratio"] == 0.6
    assert actual[0].evidence["current"]["Volume_Contraction_Ratio"] == 0.9
    assert actual[0].evidence["ended_on"] == raw.index[2].date()


def test_observation_incomplete_coverage_is_explicit_unavailable():
    scope = observation_scope(Volume_Contraction_Ratio=[0.6], Contraction_Context=[True])
    primary = SeriesInput(
        replace(scope.primary.manifest, coverage={"complete": False}), scope.primary.raw
    )
    rule = rule_request("OBSERVATION_V1", {"code": "VOLUME_CONTRACTION", "threshold": 0.7})
    item = AnalysisRequestContext().get(CalculationScope(primary, {}), (rule,)).items[0]
    assert item.state == "UNAVAILABLE"
    assert item.evidence["reasons"] == ("INCOMPLETE_PREFIX",)


def test_strict_close_breakout_requires_explicit_profile_and_reports_missing_boundary():
    rule = rule_request("chart.close_breakout.strict")
    scope = scope_for(bars([100] * 21 + [102]))
    first = AnalysisRequestContext().get(scope, (rule,)).items[0]
    assert first.state == "DETECTED"
    early = AnalysisRequestContext().get(scope_for(bars([100] * 20 + [102])), (rule,)).items[0]
    assert early.state == "UNAVAILABLE"
    assert early.evidence["reasons"] == ("HISTORY_SHORT",)
    frame = scope.primary.raw
    frame.loc[frame.index[2], "High"] = np.nan
    missing = AnalysisRequestContext().get(scope_for(frame), (rule,)).items[0]
    assert missing.state == "UNAVAILABLE"
    assert missing.evidence["reasons"] == ("INPUT_MISSING",)


@pytest.mark.parametrize(
    "low,close,volume,expected", [(99, 98, 15, True), (98, 99, 15, False), (99, 98, 14.99, False)]
)
def test_strict_low_break_uses_prior_window_and_volume_equality(low, close, volume, expected):
    frame = bars([100] * 20 + [close])
    frame.loc[frame.index[:-1], "Low"] = low
    frame.loc[frame.index[-1], "Volume"] = volume
    item = (
        AnalysisRequestContext()
        .get(scope_for(frame), (rule_request("chart.low_break_volume"),))
        .items[0]
    )
    assert item.evidence["detected"] is expected


def test_strict_weak_close_equal_location_and_volume_and_flat_range_unavailable():
    frame = bars([100] * 20 + [99])
    frame.loc[frame.index[-1], ["Open", "High", "Low", "Close", "Volume"]] = [100, 102, 98, 99, 15]
    rule = rule_request("chart.down_volume_weak_close")
    result = AnalysisRequestContext().get(scope_for(frame), (rule,)).items[0]
    assert result.evidence["detected"] is True
    frame.loc[frame.index[-1], ["Open", "High", "Low", "Close"]] = 99
    result = AnalysisRequestContext().get(scope_for(frame), (rule,)).items[0]
    assert result.state == "UNAVAILABLE"
    assert result.evidence["reasons"] == ("FLAT_RANGE",)


@pytest.mark.parametrize(
    "trigger",
    [r for r in TRIGGER_RULES if r.kind in ("cross", "slope", "supertrend", "high_breakout")],
    ids=lambda x: x.code,
)
def test_each_trigger_variant_has_positive_transition_and_strict_equality_negative(trigger):
    from src.tools.technical.chart_analysis.trigger_events import detect_trigger_events
    from src.tools.technical.triggers import detect_analysis_triggers

    frame = bars([100] * 50)
    if trigger.kind in ("cross", "high_breakout"):
        right = 0 if trigger.right == "ZERO" else 100
        if trigger.right != "ZERO":
            frame[trigger.right] = right
        frame[trigger.left] = right - 1 if trigger.sense == "up" else right + 1
        frame.loc[frame.index[-1], trigger.left] = right + (1 if trigger.sense == "up" else -1)
        equal_column, equal_value = trigger.left, right
    elif trigger.kind == "slope":
        frame[trigger.left] = 100.0
        frame.loc[frame.index[-1], trigger.left] = 101 if trigger.sense == "up" else 99
        equal_column, equal_value = trigger.left, 100.0
    else:
        target = 1 if trigger.sense == "up" else -1
        frame["SuperTrend_Dir"] = -target
        frame.loc[frame.index[-1], "SuperTrend_Dir"] = target
        equal_column, equal_value = "SuperTrend_Dir", 0
    actual = [x for x in detect_trigger_events(frame) if x.code == trigger.code]
    old = [x for x in detect_analysis_triggers(frame) if x.code == trigger.code]
    assert len(actual) == len(old) == 1
    assert actual[0].occurred_on == frame.index[-1].date()
    for key, value in asdict(actual[0]).items():
        assert value == getattr(old[0], key)
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    common = AnalysisRequestContext().get(scope, (rule_request(trigger.code),)).items
    assert len(common) == 1 and common[0].occurred_on == actual[0].occurred_on
    frame.loc[frame.index[-1], equal_column] = equal_value
    assert not [x for x in detect_trigger_events(frame) if x.code == trigger.code]


def test_trigger_vcp_invalidation_precedes_ttl_and_age_must_exceed_ttl():
    from src.tools.technical.chart_analysis.trigger_events import detect_trigger_events

    frame = bars([100] * 20 + [103] * 7)
    frame["High_20_Prev"] = 102.0
    frame["ATR"] = [10.0] * 16 + [7.0] * 11
    code = "analysis.patterns.vcp_breakout"
    for end, state in ((26, "active"), (27, "expired")):
        event = next(x for x in detect_trigger_events(frame.iloc[:end]) if x.code == code)
        assert event.status == state
    frame.loc[frame.index[-1], "Close"] = 102.0
    event = next(x for x in detect_trigger_events(frame) if x.code == code)
    assert event.status == "invalidated"
    assert event.expired_on is None


def test_common_evaluators_call_shadow_owners_when_old_public_paths_are_unavailable(monkeypatch):
    from src.tools.playbook import relative_strength
    from src.tools.technical import indicators, pivots, triggers

    def forbidden(*args, **kwargs):
        pytest.fail("common evaluator called the old public oracle")

    monkeypatch.setattr(indicators.IndicatorCalculator, "calculate", forbidden)
    monkeypatch.setattr(pivots, "confirmed_pivots", forbidden)
    monkeypatch.setattr(pivots, "confirmed_pivot_events", forbidden)
    monkeypatch.setattr(triggers, "detect_analysis_triggers", forbidden)
    monkeypatch.setattr(relative_strength, "compute_relative_strength", forbidden)
    raw = pd.read_csv("tests/fixtures/chart_analysis/seed_path.csv", index_col=0, parse_dates=True)
    primary = scope_for(raw, feature_version="LEGACY_FEATURE_AD880AF").primary
    market = SeriesInput(replace(primary.manifest, ticker="INDEX", input_hash=""), raw)
    result = AnalysisRequestContext().get(
        CalculationScope(primary, {"market": market}),
        tuple(
            rule_request(r)
            for r in (
                "legacy.indicators",
                "chart.structure_breakdown.swing",
                "analysis.macd.golden_cross",
                "chart.rs",
                "chart.pivot.span3",
            )
        ),
    )
    assert result.items


def test_preparation_backend_changes_recompute_request_local_supplied_frame(monkeypatch):
    module = import_module("src.tools.technical.chart_analysis.evaluators")
    scope = supplied_scope()
    calls = []
    original = module.prepare_legacy_frame

    def counted(series):
        calls.append(series.manifest.input_hash)
        return original(series)

    monkeypatch.setattr(module, "prepare_legacy_frame", counted)
    ctx = AnalysisRequestContext()
    ctx.get(scope, (rule_request("feature.window", {"feature_key": "Vol_SMA_5"}),))
    identity = module.legacy_fact_provider_identity

    def changed(*args, **kwargs):
        result = identity(*args, **kwargs)
        result["preparation"]["packages"]["pandas"] += "-other-build"
        return result

    monkeypatch.setattr(module, "legacy_fact_provider_identity", changed)
    ctx.get(scope, (rule_request("feature.window", {"feature_key": "Vol_SMA_5"}),))
    assert len(calls) == 2


def test_strict_close_breakout_does_not_publish_from_incomplete_final_prefix():
    frame = bars([100] * 21 + [102])
    finality = {day.date(): "FINAL" for day in frame.index}
    finality[frame.index[5].date()] = "UNKNOWN"
    item = (
        AnalysisRequestContext()
        .get(scope_for(frame, finality=finality), (rule_request("chart.close_breakout.strict"),))
        .items[0]
    )
    assert item.state == "UNAVAILABLE"
    assert item.evidence["reasons"] == ("INCOMPLETE_PREFIX",)


def test_strict_and_legacy_anchor_resolve_calculated_features_and_retain_rolling_descriptor():
    from src.tools.technical.chart_analysis.models import FeatureAnchor

    frame = bars([100] * 21 + [90])
    for fv in ("CHART_FEATURE_V1", "LEGACY_FEATURE_AD880AF"):
        scope = scope_for(frame, feature_version=fv)
        selected = FeatureAnchor(
            "sma20",
            "SUPPORT",
            frame.index[19].date(),
            frame.index[19].date(),
            100.0,
            "instrument",
            "SMA_20",
            fv,
            "ALWAYS",
            "test-source",
        )
        item = (
            AnalysisRequestContext()
            .get(scope, (rule_request("chart.anchor.break_reclaim"),), (selected,))
            .items[0]
        )
        assert item.state == "BREACHED"
        assert item.evidence["current_value"] == 99.5
        assert item.evidence["origin_price"] == 100.0


def test_rs_missing_history_has_typed_unavailable_not_an_unhandled_backend_error():
    primary = scope_for(bars([100] * 10)).primary
    market = SeriesInput(replace(primary.manifest, ticker="INDEX", input_hash=""), primary.raw)
    item = (
        AnalysisRequestContext()
        .get(CalculationScope(primary, {"market": market}), (rule_request("chart.rs"),))
        .items[0]
    )
    assert item.state == "UNAVAILABLE"
    assert item.evidence["reasons"] == ("HISTORY_SHORT",)


@pytest.mark.parametrize(
    "code,values",
    [
        ("HIGHER_HIGH", [101, 102, 103, 106, 103, 102, 101, 102, 103, 108, 103, 102, 101]),
        ("LOWER_HIGH", [101, 102, 103, 108, 103, 102, 101, 102, 103, 106, 103, 102, 101]),
        ("HIGHER_LOW", [99, 98, 97, 94, 97, 98, 99, 98, 97, 96, 97, 98, 99]),
        ("LOWER_LOW", [99, 98, 97, 96, 97, 98, 99, 98, 97, 94, 97, 98, 99]),
    ],
)
def test_every_observation_pivot_relation_matches_original_dates(code, values):
    from src.strategies.models import BarFinality
    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.observations.parameters import ObservationParameters
    from src.strategies.swing_w150.features import SwingFeatureFrame
    from src.tools.technical.scorecard_models import DataStatus

    scope = observation_scope(
        **(
            {"High": values, "Low": [99] * 13}
            if code.endswith("HIGH")
            else {"Low": values, "High": [101] * 13}
        )
    )
    frame = scope.primary.raw
    original = evaluate_observations(
        "TEST",
        SwingFeatureFrame(frame, DataStatus.COMPLETE, (BarFinality.FINAL,) * len(frame)),
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(),
    )
    expected = [x for x in original if x.code.value == code]
    actual = (
        AnalysisRequestContext().get(scope, (rule_request("OBSERVATION_V1", {"code": code}),)).items
    )
    assert len(actual) == len(expected) == 1
    assert actual[0].occurred_on == expected[0].started_on == frame.index[12].date()
    assert actual[0].evidence["pivot_on"] == expected[0].pivot_date == frame.index[9].date()


@pytest.mark.parametrize(
    "code,closes", [("UP_VOLUME_EXPANSION", [100, 101]), ("DOWN_VOLUME_EXPANSION", [100, 99])]
)
def test_each_volume_observation_threshold_equality_and_unselected_default(code, closes):
    scope = observation_scope(
        Close=closes, Volume_Ratio_Prev20=[None, 1.5], Previous_Close=[None, 100]
    )
    default = (
        AnalysisRequestContext().get(scope, (rule_request("OBSERVATION_V1", {"code": code}),)).items
    )
    assert default[0].state == "NOT_SELECTED"
    for threshold, count in ((1.5, 1), (1.5001, 0)):
        actual = (
            AnalysisRequestContext()
            .get(scope, (rule_request("OBSERVATION_V1", {"code": code, "threshold": threshold}),))
            .items
        )
        assert len(actual) == count
        if count:
            assert actual[0].occurred_on == scope.primary.raw.index[-1].date()


@pytest.mark.parametrize(
    "mode,return5,high_break,expected",
    [
        ("SMA20_TURN", -1, False, 1),
        ("SMA20_TURN_POSITIVE_RETURN", 0, False, 0),
        ("SMA20_TURN_POSITIVE_RETURN", 0.1, False, 1),
        ("SMA20_TURN_HIGH_BREAK", 0.1, False, 0),
        ("SMA20_TURN_HIGH_BREAK", 0, True, 1),
    ],
)
def test_reacceleration_modes_preserve_explicit_positive_return_and_high_break(
    mode, return5, high_break, expected
):
    scope = observation_scope(
        Close=[99, 101],
        SMA_20=[100, 100],
        SMA_20_Slope_5=[-1, 1],
        Previous_SMA20_Slope=[0, -1],
        Prior_Trend_Context=[True, True],
        Prior_Below_SMA20=[True, True],
        Return_5=[0, return5],
        High_Break_5=[False, high_break],
    )
    items = (
        AnalysisRequestContext()
        .get(scope, (rule_request("chart.momentum.reacceleration", {"mode": mode}),))
        .items
    )
    assert len(items) == expected


def test_deceleration_missing_context_preserves_previous_episode_status():
    scope = observation_scope(
        Close=[95, 95, 95],
        SMA_20=[100] * 3,
        SMA_20_Slope_5=[-1, -2, -3],
        Previous_SMA20_Slope=[0, -1, -2],
        Prior_Trend_Context=[True, None, True],
    )
    items = (
        AnalysisRequestContext().get(scope, (rule_request("chart.momentum.deceleration"),)).items
    )
    assert len(items) == 1 and items[0].state == "ACTIVE"
    assert items[0].status_as_of == scope.primary.raw.index[-1].date()


@pytest.mark.parametrize(
    "rule",
    [
        "chart.vcp.legacy",
        "chart.pocket_pivot.down_candle",
        "chart.power_gap",
        "chart.close_breakout.nanmax",
    ],
)
def test_legacy_family_missing_prerequisites_is_explicit_unavailable(rule):
    scope = scope_for(bars([100]), feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    result = AnalysisRequestContext().get(scope, (rule_request(rule),)).items[0]
    assert result.state == "UNAVAILABLE"
    assert result.evidence["reasons"] == ("HISTORY_SHORT",)


def test_selected_nonzero_anchor_buffers_remain_supported_and_use_computed_atr():
    from src.tools.technical.chart_analysis.models import FixedPriceAnchor

    frame = bars([100] * 21 + [97])
    scope = scope_for(frame)
    selected = FixedPriceAnchor(
        "fixed",
        "SUPPORT",
        frame.index[0].date(),
        frame.index[0].date(),
        100.0,
        100.0,
        "FINAL",
        "source",
    )
    rule = rule_request(
        "chart.anchor.break_reclaim", {"break_buffer_atr": 1.0, "reclaim_buffer_atr": 0.5}
    )
    item = AnalysisRequestContext().get(scope, (rule,), (selected,)).items[0]
    assert item.state == "BREACHED"
    assert item.evidence["current_value"] == 100.0


def test_public_common_anchor_resolver_selects_strict_or_legacy_provider_without_supplied_columns():
    from src.tools.technical.chart_analysis.detectors import resolve_anchor_feature
    from src.tools.technical.chart_analysis.models import FeatureAnchor

    frame = bars([100] * 21 + [90])
    for fv in ("CHART_FEATURE_V1", "LEGACY_FEATURE_AD880AF"):
        series = scope_for(frame, feature_version=fv).primary
        selected = FeatureAnchor(
            "sma20",
            "SUPPORT",
            frame.index[19].date(),
            frame.index[19].date(),
            100.0,
            "instrument",
            "SMA_20",
            fv,
            "ALWAYS",
            "test-source",
        )
        values = resolve_anchor_feature(series, selected)
        assert values.iloc[-1] == 99.5
        assert pd.isna(values.iloc[18])


def test_each_anchor_backend_contributes_to_union_analysis_identity(monkeypatch):
    from src.tools.technical.chart_analysis.models import FeatureAnchor

    module = import_module("src.tools.technical.chart_analysis.evaluators")
    frame = bars([100] * 21 + [90])
    scope = scope_for(frame)
    common = {
        "kind": "SUPPORT",
        "origin_on": frame.index[19].date(),
        "available_on": frame.index[19].date(),
        "origin_value": 100.0,
        "input_role": "instrument",
        "active_when": "ALWAYS",
        "source_id": "test",
    }
    strict = FeatureAnchor(
        id="strict", feature_key="SMA_20", feature_version="CHART_FEATURE_V1", **common
    )
    rolling = FeatureAnchor(
        id="rolling", feature_key="SMA_20", feature_version="SMA_ROLLING_V1", **common
    )
    rule = rule_request("chart.anchor.break_reclaim")
    ctx = AnalysisRequestContext()
    first = ctx.get(scope, (rule,), (strict, rolling))
    original = module.feature_api.feature_provider_identity

    def changed(fv):
        result = original(fv)
        if fv == "CHART_FEATURE_V1":
            result["backend"] += "/revision"
        return result

    monkeypatch.setattr(module.feature_api, "feature_provider_identity", changed)
    second = ctx.get(scope, (rule,), (strict, rolling))
    assert first.analysis_id != second.analysis_id
    first_by_anchor = {x.anchor_id: x for x in first.items}
    second_by_anchor = {x.anchor_id: x for x in second.items}
    assert first_by_anchor["strict"].evaluation_key != second_by_anchor["strict"].evaluation_key
    assert first_by_anchor["rolling"] is second_by_anchor["rolling"]


def test_strict_breakout_identity_includes_actual_strict_prefix_provider(monkeypatch):
    module = import_module("src.tools.technical.chart_analysis.evaluators")
    scope = scope_for(bars([100] * 21 + [102]))
    rule = rule_request("chart.close_breakout.strict")
    ctx = AnalysisRequestContext()
    first = ctx.get(scope, (rule,))
    original = module.feature_api.feature_provider_identity

    def changed(fv):
        result = original(fv)
        result["backend"] += "/changed-prefix-provider"
        return result

    monkeypatch.setattr(module.feature_api, "feature_provider_identity", changed)
    second = ctx.get(scope, (rule,))
    assert first.analysis_id != second.analysis_id
    assert first.items[0].evaluation_key != second.items[0].evaluation_key


def test_market_only_fact_uses_market_identity_and_short_history_is_unavailable():
    scope = supplied_scope()
    primary = SeriesInput(replace(scope.primary.manifest, ticker="OTHER"), scope.primary.raw)
    rule = rule_request("chart.market.regime")
    actual = (
        AnalysisRequestContext().get(CalculationScope(primary, scope.related), (rule,)).items[0]
    )
    original = AnalysisRequestContext().get(scope, (rule,)).items[0]
    assert actual.id == original.id
    short_raw = scope.related["market"].raw.iloc[:30]
    short_market = SeriesInput(
        replace(scope.related["market"].manifest, input_hash="", as_of=short_raw.index[-1].date()),
        short_raw,
    )
    short = (
        AnalysisRequestContext()
        .get(CalculationScope(primary, {"market": short_market}), (rule,))
        .items[0]
    )
    assert short.state == "UNAVAILABLE"
    assert short.evidence["reasons"] == ("HISTORY_SHORT",)
