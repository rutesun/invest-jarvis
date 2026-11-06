"""Common facts must replace numerical detectors while preserving strategy policy."""

from dataclasses import replace

import pandas as pd
import pytest

from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.strategies.swing_w150.signals import detect_swing
from tests.strategies.swing_w150.conftest import SignalFactory
from tests.strategies.swing_w150.test_features import _raw_ohlcv


def test_supplied_common_facts_replace_v2_price_and_structure_detectors(monkeypatch):
    import src.strategies.swing_w150.signals as signals
    from src.strategies.swing_w150.common import swing_analysis

    params = SwingW150Parameters()
    features = SignalFactory().same_day_exit_and_entry()
    expected = detect_swing("TEST", features, params).model_dump(mode="json")
    analysis = swing_analysis("TEST", features, params)

    def forbidden(*args, **kwargs):
        raise AssertionError("old numerical detector called")

    for name in (
        "structure_breakdown",
        "deep_recovery",
        "_trend_breakout",
        "_deep_recovery",
        "confirmed_pivot_events",
    ):
        monkeypatch.setattr(signals, name, forbidden, raising=False)
    actual = detect_swing("TEST", features, params, common_analysis=analysis)
    assert actual.model_dump(mode="json") == expected
    assert actual.common_analyses == (analysis,)
    assert any(selection.selected for selection in actual.fact_selections)


def test_raw_feature_injection_bypasses_old_indicator_and_pivot_bodies(monkeypatch):
    import src.strategies.swing_w150.features as features_module
    from src.strategies.swing_w150.common import raw_swing_analysis

    raw = _raw_ohlcv()
    params = SwingW150Parameters()
    expected = build_swing_features(raw, params)
    analysis = raw_swing_analysis(raw, params)

    def forbidden(*args, **kwargs):
        raise AssertionError("old feature detector called")

    from src.tools.technical.indicators import IndicatorCalculator

    monkeypatch.setattr(IndicatorCalculator, "calculate", forbidden)
    monkeypatch.setattr(features_module, "confirmed_pivots", forbidden, raising=False)
    actual = build_swing_features(raw, params, common_analysis=analysis)
    pd.testing.assert_frame_equal(actual.frame, expected.frame)
    for changed_raw in (raw.iloc[:-1], raw.iloc[:249]):
        with pytest.raises(ValueError, match="scope"):
            build_swing_features(changed_raw, params, common_analysis=analysis)


def test_swing_rejects_stale_fact_scope_and_wrong_selected_parameters():
    from src.strategies.swing_w150.common import swing_analysis

    params = SwingW150Parameters()
    features = SignalFactory().same_day_exit_and_entry()
    analysis = swing_analysis("TEST", features, params)
    with pytest.raises(ValueError, match="scope"):
        detect_swing("OTHER", features, params, common_analysis=analysis)
    with pytest.raises(ValueError, match="request|parameter"):
        detect_swing(
            "TEST",
            features,
            replace(params, trend_breakout_volume_multiple=2),
            common_analysis=analysis,
        )


def test_v1_replay_injection_keeps_all_trade_and_transition_values(monkeypatch):
    from src.strategies.swing_w150 import engine, rules
    from src.strategies.swing_w150.common import raw_swing_analysis
    from tests.strategies.swing_w150.conftest import load_prices

    raw = load_prices("UPST")
    expected = engine.replay_trace(raw)
    analysis = raw_swing_analysis(raw, SwingW150Parameters())

    def forbidden(*args, **kwargs):
        raise AssertionError("old replay numerical body called")

    from src.tools.technical.indicators import IndicatorCalculator

    monkeypatch.setattr(IndicatorCalculator, "calculate", forbidden)
    for name in (
        "s_trigger",
        "d_trigger",
        "structure_breakdown",
        "deep_recovery",
        "confirmed_pivots",
    ):
        monkeypatch.setattr(rules, name, forbidden)
    assert engine.replay_trace(raw, common_analysis=analysis) == expected


def test_s01_injected_fact_controls_signal_selection():
    from src.strategies.swing_w150.common import swing_analysis

    params = SwingW150Parameters()
    features = SignalFactory().make([{"Close": 150, "High": 151, "Volume": 200}])
    analysis = swing_analysis("TEST", features, params)
    item = next(item for item in analysis.items if item.rule_id == "chart.close_breakout.strict")
    values = dict(item.evidence)
    values["trigger"] = (*values["trigger"][:-1], False)
    changed = replace(
        analysis,
        items=tuple(replace(x, evidence=values) if x is item else x for x in analysis.items),
    )
    assert [
        x.code
        for x in detect_swing("TEST", features, params, common_analysis=analysis).current_signals
    ] == ["TREND_BREAKOUT_ENTRY"]
    assert not detect_swing("TEST", features, params, common_analysis=changed).current_signals


def test_adapter_retains_original_bundle_scope_and_resolvable_refs():
    from src.strategies.swing_w150.adapter import SwingW150SignalStrategy
    from tests.strategies.test_common_chart_parity import _bundle

    bundle = _bundle(_raw_ohlcv(), provisional=True)
    result = SwingW150SignalStrategy().evaluate_signals(bundle)
    assert not result.diagnostic_errors
    assert result.fact_selections and result.common_analyses
    analyses = {analysis.analysis_id: analysis for analysis in result.common_analyses}
    assert all(
        analysis.manifest.input_profile == bundle.profile_version for analysis in analyses.values()
    )
    assert all(
        analysis.manifest.finality[bundle.as_of] == "PROVISIONAL" for analysis in analyses.values()
    )
    for selection in result.fact_selections:
        assert any(
            item.id == selection.ref.item_id for item in analyses[selection.ref.analysis_id].items
        )
    assert "common_analyses" not in result.model_dump()


@pytest.mark.parametrize("bars", [249, 250, 251])
def test_raw_common_feature_history_boundary_is_unchanged(bars):
    from src.tools.technical.scorecard_models import DataStatus

    features = build_swing_features(_raw_ohlcv().iloc[:bars], SwingW150Parameters())
    assert features.data_status == (
        DataStatus.INSUFFICIENT_DATA if bars == 249 else DataStatus.COMPLETE
    )
    assert len(features.frame) == bars


def test_v1_adapter_retains_referenced_immutable_analyses():
    from src.strategies.swing_w150.adapter import SwingW150Strategy
    from tests.strategies.test_common_chart_parity import _bundle

    result = SwingW150Strategy().evaluate(_bundle(_raw_ohlcv(), listing=True))
    assert result.common_analyses and result.fact_selections
    analyses = {a.analysis_id: a for a in result.common_analyses}
    for selection in result.fact_selections:
        assert any(
            item.id == selection.ref.item_id for item in analyses[selection.ref.analysis_id].items
        )


def test_supplied_custom_slope_window_never_requires_default_window_columns():
    params = replace(
        SwingW150Parameters(), parameter_set_version="CUSTOM_SLOPE_7", direction_lookback_bars=7
    )
    features = SignalFactory().make([{"Close": 150, "High": 151, "Volume": 200}])
    frame = features.frame.rename(
        columns={f"SMA_{period}_Slope_21": f"SMA_{period}_Slope_7" for period in (50, 150, 200)}
    )
    result = detect_swing("TEST", replace(features, frame=frame), params)
    assert [signal.code for signal in result.current_signals] == ["TREND_BREAKOUT_ENTRY"]
