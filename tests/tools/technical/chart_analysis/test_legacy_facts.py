"""Numerical ownership: independent old bodies and literal boundary oracles."""

from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.chart_analysis.models import CalculationScope
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


def api():
    return import_module("src.tools.technical.chart_analysis.legacy_facts")


def facts(frame, family):
    return api().legacy_fact_values_from_frame(frame, family=family)


def seed():
    path = Path("tests/fixtures/chart_analysis/seed_path.csv")
    return pd.read_csv(path, index_col=0, parse_dates=True)


def test_new_frame_api_owns_raw_vcp_boundary_before_consumer_rounding():
    frame = bars([100.0] * 20)
    frame["ATR"] = [10.0] * 16 + [7.996] * 4
    result = facts(frame, "chart.vcp.legacy")
    assert result["atr_contraction_ratio"] == pytest.approx(0.2004)
    assert round(result["atr_contraction_ratio"], 3) == 0.2
    assert result["in_vcp"] is True
    assert result["strong"] is True


def test_context_compares_rounded_ratio_and_equal_sma_is_not_above():
    frame = bars([100.0] * 20)
    frame["SMA_20"] = frame["SMA_50"] = 100.0
    frame["Vol_SMA_20"] = 200.0
    frame.loc[frame.index[-1], "Volume"] = 259.0
    result = facts(frame, "chart.context.breakdown")
    assert result["volume_ratio_raw"] == 1.295
    assert result["volume_ratio_20d"] == 1.29  # Python float round at the old consumer point
    assert result["is_breakdown"] is False
    frame.loc[frame.index[-1], "Volume"] = 259.01
    result = facts(frame, "chart.context.breakdown")
    assert result["close_above_sma50"] is False
    assert result["volume_ratio_20d"] == 1.3
    assert result["is_breakdown"] is True


def test_pocket_pivot_keeps_down_candle_and_tennis_reference_window():
    frame = bars([100.0] * 11)
    frame["Open"] = 101.0
    frame["SMA_50"] = 100.0
    frame["Vol_SMA_20"] = 10.0
    frame.loc[frame.index[-1], "Volume"] = 20.0
    assert facts(frame, "chart.pocket_pivot.down_candle")["detected"] is True
    frame.loc[frame.index[-1], "Open"] = 99.0
    assert facts(frame, "chart.pocket_pivot.down_candle")["detected"] is False


def test_separate_window_owner_preserves_supplied_columns_and_exact_indicator_columns():
    from src.strategies.swing_w150.features import observation_feature_columns
    from src.tools.technical.indicators import IndicatorCalculator

    raw = seed()
    original = IndicatorCalculator().calculate(raw)
    expected = observation_feature_columns(original)
    result = api().calculate_legacy_windows(original)
    for key in expected.columns.difference(original.columns):
        pd.testing.assert_series_equal(result[key], expected[key])
    assert "Vol_SMA_5" not in original
    assert result["Vol_SMA_5"].iloc[-1] == raw["Volume"].iloc[-5:].mean()
    assert result["Vol_SMA_20_Shift5"].iloc[-1] == raw["Volume"].iloc[-25:-5].mean()
    original["Vol_SMA_5"] = 123.0
    assert (api().calculate_legacy_windows(original)["Vol_SMA_5"] == 123).all()


@pytest.mark.parametrize(
    "csv",
    [
        "tests/fixtures/chart_analysis/seed_path.csv",
        "tests/fixtures/swing_w150/COIN.csv",
        "tests/fixtures/swing_w150/AMAT.csv",
    ],
)
def test_real_source_component_conditions_equal_independent_old_bodies(csv):
    from src.tools.technical.components.crsi import analyze_crsi
    from src.tools.technical.components.divergence import analyze_divergence
    from src.tools.technical.components.minervini import analyze_minervini
    from src.tools.technical.components.patterns import (
        _detect_breakout,
        _detect_candlestick_patterns,
        _detect_vcp,
    )
    from src.tools.technical.components.risk import analyze_risk
    from src.tools.technical.components.supertrend import analyze_supertrend
    from src.tools.technical.components.velocity import analyze_velocity
    from src.tools.technical.components.volume import (
        _detect_pocket_pivot,
        _detect_power_gap_up,
        analyze_volume,
    )
    from src.tools.technical.context import build_market_context
    from src.tools.technical.indicators import IndicatorCalculator

    raw = pd.read_csv(csv, index_col=0, parse_dates=True)
    for n in (50, 200, len(raw)):
        frame = IndicatorCalculator().calculate(raw.iloc[:n])
        result = facts(frame, "chart.vcp.legacy")
        old = _detect_vcp(frame)
        assert result["in_vcp"] == (old["score"] > 0)
        assert result["strong"] == (old["score"] == 20)
        for key, val in old["metrics"].items():
            assert result["metrics"][key] == val
        assert (
            facts(frame, "chart.pocket_pivot.down_candle")["detected"]
            == _detect_pocket_pivot(frame, frame.iloc[-1])["detected"]
        )
        assert (
            facts(frame, "chart.power_gap")["detected"] == _detect_power_gap_up(frame)["detected"]
        )
        ctx = facts(frame, "chart.context.breakdown")
        for key, val in build_market_context(frame).model_dump().items():
            assert ctx[key] == val
        for family, old_component in [
            ("chart.stage2.minervini", analyze_minervini),
            ("chart.velocity.legacy", analyze_velocity),
            ("chart.crsi.legacy", analyze_crsi),
            ("chart.supertrend.legacy", analyze_supertrend),
            ("legacy.confluence", analyze_risk),
            ("legacy.divergence", analyze_divergence),
            ("chart.legacy.volume_extra", analyze_volume),
        ]:
            result = facts(frame, family)
            for key, val in old_component(frame).metrics.items():
                assert result["metrics"][key] == val
        patterns = facts(frame, "chart.legacy.patterns_extra")
        for old in (_detect_breakout(frame), _detect_candlestick_patterns(frame)):
            for key, val in old["metrics"].items():
                assert patterns["metrics"][key] == val


def test_velocity_suppresses_negative_conditions_above_sma20():
    frame = bars([101.0] * 20)
    frame["SMA_20"] = np.linspace(101.9, 100, 20)
    result = facts(frame, "chart.velocity.legacy")
    assert result["norm_slope"] < -0.05
    assert result["price_above_sma20"] is True
    assert result["downward"] is False
    assert result["turn_down"] is False


def test_strict_breakout_and_nanmax_breakout_remain_distinct():
    frame = bars([100.0] * 22)
    frame.loc[frame.index[-1], "Close"] = 105.0
    frame.loc[frame.index[5], "High"] = np.nan
    strict = api().close_breakout_values(frame, lookback=20)
    legacy = facts(frame, "chart.close_breakout.nanmax")
    assert not strict["fresh"][-1]
    assert legacy["fresh"] is True


def test_swing_arrays_match_original_rules_including_flat_range_fallback():
    from src.strategies.swing_w150 import rules
    from src.tools.technical.indicators import IndicatorCalculator
    from src.tools.technical.pivots import confirmed_pivots

    frame = IndicatorCalculator().calculate(seed())
    frame.loc[frame.index[-1], ["High", "Low", "Close"]] = 100.0
    st = np.nan_to_num(frame["SuperTrend_Dir"].to_numpy(float), nan=1.0)
    higher_low, lhll = confirmed_pivots(frame["High"].to_numpy(float), frame["Low"].to_numpy(float))
    result = api().swing_numerical_values(
        frame, st=st, higher_low=higher_low, lower_low_lower_high=lhll
    )
    hb = rules.structure_breakdown(frame, st, lhll)
    deep = rules.deep_recovery(frame, st, hb, higher_low)
    for key, want in [
        ("structure_breakdown", hb),
        ("deep_recovery", deep),
        ("s_trigger", rules.s_trigger(frame)),
        ("d_trigger", rules.d_trigger(frame, deep)),
    ]:
        np.testing.assert_array_equal(result[key], want)
    assert result["close_location"][-1] == 0.5


def test_playbook_raw_owners_equal_old_and_short_flat_range_is_one():
    from src.tools.playbook.accumulation import analyze_accumulation
    from src.tools.playbook.market_regime import assess_market_regime
    from src.tools.playbook.relative_strength import compute_relative_strength
    from src.tools.playbook.vcp import detect_vcp_breakout
    from src.tools.technical.indicators import IndicatorCalculator

    raw = seed()
    frame = IndicatorCalculator().calculate(raw)
    vcp = facts(frame, "chart.vcp.playbook")
    old = detect_vcp_breakout(frame)
    assert (vcp["in_vcp"], vcp["pivot"], vcp["breakout"]) == (old.in_vcp, old.pivot, old.breakout)
    accumulation = facts(frame, "chart.accumulation.days")
    for key, val in analyze_accumulation(frame).model_dump(exclude={"is_accumulating"}).items():
        assert accumulation[key] == val
    market = api().market_regime_values(raw)
    assert market["regime"] == assess_market_regime(raw, "MKT").regime
    other = raw.copy()
    other["Close"] = np.linspace(100, 110, len(raw))
    other.loc[other.index[10], "Close"] = np.nan
    rs = api().relative_strength_values(raw, other)
    for key, val in compute_relative_strength(raw, other, "MKT").model_dump().items():
        if key not in ("index_symbol", "is_strong"):
            assert rs[key] == val
    flat = bars([100, 101])
    flat["High"] = flat["Low"] = flat["Close"]
    flat["Volume"] = [10, 20]
    assert facts(flat, "chart.accumulation.days")["accumulation_days"] == 1


def test_fixed_anchor_comparisons_keep_equal_reclaim_and_fixed_signal_atr():
    result = api().fixed_anchor_close_values(
        90, breakout_level=90, origin_support=95, pullback_low=92, signal_close=120, signal_atr=10
    )
    assert result["below_breakout"] is False
    assert result["at_or_above_breakout"] is True
    assert result["below_origin"] is True
    assert result["below_pullback"] is True
    assert result["at_or_below_signal_minus_3atr"] is True


def test_facade_rejects_strict_scope_preserves_supplied_frames_and_identity():
    frame = bars([100.0] * 30)
    frame["ATR"] = [10.0] * 26 + [7.996] * 4
    original = frame.copy(deep=True)
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    digest = scope.primary.manifest.input_hash
    assert api().legacy_fact_values(scope, family="chart.vcp.legacy")["in_vcp"] is True
    assert scope.primary.manifest.input_hash == digest
    pd.testing.assert_frame_equal(frame, original)
    with pytest.raises(ValueError, match="legacy"):
        api().legacy_fact_values(scope_for(frame), family="chart.vcp.legacy")
    with pytest.raises(KeyError, match="Unknown"):
        api().legacy_fact_values(scope, family="unknown")


def test_rs_scope_uses_both_raw_series_without_old_function(monkeypatch):
    import src.tools.playbook.relative_strength as old

    def forbidden(*args, **kwargs):
        raise AssertionError("old consumer called")

    monkeypatch.setattr(old, "compute_relative_strength", forbidden)
    raw = bars(np.linspace(100, 140, 50))
    market = bars([100.0] * 50)
    stock_scope = scope_for(raw, feature_version="LEGACY_FEATURE_AD880AF")
    market_scope = scope_for(market, feature_version="LEGACY_FEATURE_AD880AF")
    scope = CalculationScope(stock_scope.primary, {"market": market_scope.primary})
    result = api().legacy_fact_values(scope, family="chart.rs")
    assert result["mansfield_rs"] == 16.67
    assert result["strong"] is True


def test_fixed_anchor_keeps_decimal_comparison_precision_and_missing_values():
    from decimal import Decimal

    result = api().fixed_anchor_close_values(
        Decimal("100"), breakout_level=Decimal("100.00000000000000001")
    )
    assert result["below_breakout"] is True
    assert result["below_origin"] is None
    assert result["at_or_below_signal_minus_3atr"] is None


def test_swing_v2_explicit_comparisons_differ_from_replay_nan_fallback():
    from src.tools.technical.chart_analysis._legacy_structure import swing_s01_values

    frame = bars([100.0] * 52)
    for key, value in {
        "SMA_20": 90.0,
        "SMA_50": 95.0,
        "SMA_150": 90.0,
        "SMA_200": 120.0,
        "SMA_150_Slope_21": 1.0,
        "SMA_20_Slope_5": 1.0,
        "Vol_SMA_20": 10.0,
        "Vol_SMA_20_Prev": 10.0,
        "High_20_Prev": 101.0,
        "High_50_Prev": 101.0,
        "Low_20_Prev": 90.0,
    }.items():
        frame[key] = value
    frame = api().calculate_legacy_windows(frame)
    frame.loc[frame.index[-1], ["Close", "Volume"]] = [105.0, 20.0]
    result = api().swing_signal_values(frame)
    assert result["trend_breakout"][-1]
    assert result["deep_recovery_trigger"][-1]
    frame.loc[frame.index[-2], "Close"] = np.nan
    assert not api().swing_signal_values(frame)["trend_breakout"][-1]
    assert swing_s01_values(frame, comparison_profile="V1_REPLAY")["trigger"][-1]
    assert not swing_s01_values(
        frame, reference_column="Trend_Breakout_High_Prev", comparison_profile="V2_SIGNAL"
    )["trigger"][-1]


def test_swing_structure_families_have_actual_numerical_facade_and_no_implicit_pivots():
    from src.tools.technical.indicators import IndicatorCalculator

    frame = IndicatorCalculator().calculate(seed())
    frame["Higher_Low"] = False
    frame["Lower_Low_Lower_High"] = False
    frame["SuperTrend_Dir"] = 1
    assert "structure_breakdown" in facts(frame, "chart.structure_breakdown.swing")
    assert "deep_recovery" in facts(frame, "chart.deep_recovery.swing")
    del frame["Higher_Low"]
    with pytest.raises(ValueError, match="pivot"):
        facts(frame, "chart.deep_recovery.swing")


def test_observation_conditions_are_raw_arrays_without_episode_or_threshold_policy():
    frame = bars([100.0] * 30)
    frame["SMA_20"] = 100.0
    frame["SMA_150"] = 90.0
    frame["SMA_150_Slope_21"] = 0.0
    frame["SMA_20_Slope_5"] = 0.0
    frame.loc[frame.index[-2], "Close"] = 99.0
    frame.loc[frame.index[-1], ["Close", "SMA_20_Slope_5"]] = [102.0, 1.0]
    values = api().observation_numerical_values(frame)
    assert bool(values["Reacceleration_Turn"].iloc[-1]) is True
    assert bool(values["Reacceleration_Positive_Return"].iloc[-1]) is True
    assert bool(values["Reacceleration_High_Break"].iloc[-1]) is True
    assert bool(values["Momentum_Weak_Start"].iloc[-1]) is False


@pytest.mark.parametrize("count", [1, 2, 19, 20, 21, 199, 200, 220, 253])
def test_rs_exact_short_window_fallback_or_legacy_error(count):
    from src.tools.playbook.relative_strength import compute_relative_strength

    stock, market = bars(np.linspace(100, 110, count)), bars([100.0] * count)
    if 2 <= count < 20:
        with pytest.raises(ValueError, match="min_periods"):
            compute_relative_strength(stock, market, "MKT")
        with pytest.raises(ValueError, match="min_periods"):
            api().relative_strength_values(stock, market)
    else:
        original = compute_relative_strength(stock, market, "MKT")
        result = api().relative_strength_values(stock, market)
        assert result["mansfield_rs"] == original.mansfield_rs
        assert result["rp_slope_4w"] == original.rp_slope_4w
        assert result["outperform_6m"] == original.outperform_6m


def test_divergence_occurrences_match_independent_reference_on_nan_prefixes():
    from scipy.signal import argrelextrema

    from src.tools.technical.components.divergence import (
        _detect_bearish_divergence,
        _detect_bullish_divergence,
        _detect_crsi_divergence,
        _detect_macd_divergence,
    )

    frame = bars(100 + 5 * np.sin(np.arange(80) / 3) + np.arange(80) / 10)
    frame["RSI"] = 50 + 20 * np.sin(np.arange(80) / 3) - np.arange(80) / 10
    frame["MACD"] = frame["RSI"]
    frame["cRSI"] = frame["RSI"]
    frame.loc[frame.index[5], ["RSI", "MACD", "cRSI"]] = np.nan
    seen = False
    for n in range(60, 81):
        prefix = frame.iloc[:n]
        price, rsi = prefix["Close"].values, prefix["RSI"].fillna(50).values
        ph, pl = (argrelextrema(price, compare, order=5)[0] for compare in (np.greater, np.less))
        rh, rl = (argrelextrema(rsi, compare, order=5)[0] for compare in (np.greater, np.less))
        result = facts(prefix, "legacy.divergence")
        for key, old in [
            ("rsi_bearish", _detect_bearish_divergence(prefix, ph, rh, price, rsi)),
            ("rsi_bullish", _detect_bullish_divergence(prefix, pl, rl, price, rsi)),
            ("macd", _detect_macd_divergence(prefix, ph, pl, price)),
            ("crsi", _detect_crsi_divergence(prefix, ph, pl, price)),
        ]:
            assert bool(result[key]) == bool(old)
            seen = seen or bool(old)
            if old:
                assert result[key]["bias"] == ("bearish" if old["score"] < 0 else "bullish")
    assert seen


def test_stage2_uses_shift21_low_equality_and_sma_strict_equality():
    frame = bars([130.0] * 200)
    for key, value in {
        "SMA_50": 120.0,
        "SMA_150": 110.0,
        "SMA_200": 100.0,
        "High_52w": 170.0,
        "Low_52w": 100.0,
    }.items():
        frame[key] = value
    frame.loc[frame.index[-22], ["SMA_150", "SMA_200"]] = [109.0, 99.0]
    frame.loc[frame.index[-21], ["SMA_150", "SMA_200"]] = [111.0, 101.0]
    result = facts(frame, "chart.stage2.minervini")
    assert result["is_stage2"] is True
    assert result["conditions"]["above_52w_low_30pct"] is True
    frame.loc[frame.index[-1], "SMA_50"] = 130.0
    assert facts(frame, "chart.stage2.minervini")["conditions"]["above_50"] is False
    assert facts(frame.iloc[:-1], "chart.stage2.minervini")["available"] is False


def test_vcp_dropna_and_distinct_playbook_volume50_boundary():
    frame = bars([100.0] * 30)
    frame["ATR"] = [np.nan] * 21 + [10.0] * 4 + [np.nan] + [7.996] * 4
    frame["Vol_SMA_20"] = 10.0
    frame["Vol_SMA_50"] = 100.0
    frame.loc[frame.index[-1], ["Close", "Volume"]] = [110.0, 149.0]
    result = facts(frame, "chart.vcp.playbook")
    assert result["in_vcp"] is True
    assert result["vcp"]["atr_contraction_ratio"] == pytest.approx(0.2004)
    assert result["vol_ok"] is False
    assert result["breakout"] is False
    frame.loc[frame.index[-1], "Volume"] = 150.0
    assert facts(frame, "chart.vcp.playbook")["breakout"] is True


def test_wick_breakout_and_power_gap_keep_their_own_references():
    frame = bars([99.0] * 22)
    frame["Vol_SMA_20"] = 20.0
    frame.loc[frame.index[-1], ["High", "Close", "Open", "Volume"]] = [110.0, 99.0, 104.0, 60.0]
    assert facts(frame, "chart.legacy.patterns_extra")["high_breakout"] is True
    assert not api().close_breakout_values(frame)["fresh"][-1]
    gap = facts(frame, "chart.power_gap")
    assert gap["detected"] is True
    assert gap["previous_high"] == 100.0
    assert gap["gap_vol_ratio"] == 3.0
    frame.loc[frame.index[-1], "Open"] = 103.999
    assert facts(frame, "chart.power_gap")["detected"] is False


def test_scope_provider_is_real_and_does_not_call_old_component_or_indicator(monkeypatch):
    import src.tools.technical.components.patterns as patterns
    from src.tools.technical.chart_analysis.features import feature_provider_identity
    from src.tools.technical.indicators import IndicatorCalculator

    def forbidden(*args, **kwargs):
        raise AssertionError("old consumer called")

    monkeypatch.setattr(IndicatorCalculator, "calculate", forbidden)
    monkeypatch.setattr(patterns, "_detect_vcp", forbidden)
    raw = seed()
    legacy = scope_for(raw, feature_version="LEGACY_FEATURE_AD880AF")
    original = legacy.primary.raw
    result = api().legacy_fact_values(legacy, family="chart.vcp.legacy")
    assert "atr_contraction_ratio" in result
    identity = feature_provider_identity(legacy.primary.manifest.feature_version)
    assert identity["backend"].startswith("pandas-ta/")
    supplied = scope_for(raw, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    assert (
        feature_provider_identity(supplied.primary.manifest.feature_version)["backend"]
        == "supplied-columns"
    )
    pd.testing.assert_frame_equal(legacy.primary.raw, original)


def test_facade_swing_scope_uses_legacy_unmasked_pivots_without_mutating_input():
    raw = seed()
    scope = scope_for(raw, feature_version="LEGACY_FEATURE_AD880AF")
    result = api().legacy_fact_values(scope, family="chart.structure_breakdown.swing")
    assert len(result["structure_breakdown"]) == len(raw)
    assert "Higher_Low" not in scope.primary.raw


def test_feature_window_family_returns_separate_derived_frame():
    result = facts(seed(), "feature.window")
    assert result["frame"]["Vol_SMA_5"].iloc[-1] == seed()["Volume"].iloc[-5:].mean()


def test_identity_reports_the_actual_raw_close_backend_and_dependency_roles():
    frame = bars([100.0] * 30)
    stock = scope_for(frame, feature_version="LEGACY_FEATURE_AD880AF").primary
    market = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF").primary
    scope = CalculationScope(stock, {"market": market})
    identities = api().legacy_fact_provider_identity(scope, family="chart.rs")
    assert set(identities["providers"]) == {"instrument", "market"}
    assert {item["backend"] for item in identities["providers"].values()} == {"pandas/raw-close"}
    assert set(
        api().legacy_fact_provider_identity(scope, family="chart.market.regime")["providers"]
    ) == {"market"}
    supplied = CalculationScope(market, {})
    assert (
        api().legacy_fact_provider_identity(supplied, family="chart.vcp.legacy")["providers"][
            "instrument"
        ]["backend"]
        == "supplied-columns"
    )


def test_context_preserves_raw_returns_distances_and_rounded_comparison_points():
    frame = bars([100.0] * 5 + [114.9998])
    frame["SMA_20"] = 100.0
    result = facts(frame, "chart.context.breakdown")
    assert result["ret_5d_raw"] == pytest.approx(14.9998)
    assert result["ret_5d"] == 15.0
    assert result["distance_from_sma20_pct_raw"] == pytest.approx(14.9998)
    assert result["is_overextended"] is True


@pytest.mark.parametrize(
    "family,backend,calculation_packages",
    [
        ("feature.window", "pandas/rolling-shift", {"pandas", "numpy"}),
        ("legacy.divergence", "scipy/argrelextrema", {"pandas", "numpy", "scipy"}),
        ("chart.velocity.legacy", "numpy/polyfit", {"pandas", "numpy"}),
    ],
)
def test_supplied_identity_separates_feature_provenance_from_live_calculation_versions(
    family, backend, calculation_packages
):
    from importlib.metadata import version

    frame = bars([100.0] * 63)
    frame["SMA_20"] = np.linspace(90, 100, len(frame))
    frame["RSI"] = 50.0
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    result = api().legacy_fact_values(scope, family=family)
    assert "frame" in result or result["available"] is True
    identity = api().legacy_fact_provider_identity(scope, family=family)
    assert identity["providers"]["instrument"]["backend"] == "supplied-columns"
    expected_preparation = (
        {
            "backend": "pandas/rolling-shift",
            "packages": {name: version(name) for name in ("pandas", "numpy")},
        }
        if family == "feature.window"
        else None
    )
    assert identity["preparation"] == expected_preparation
    assert identity["calculation"] == {
        "backend": backend,
        "packages": {name: version(name) for name in calculation_packages},
    }


@pytest.mark.parametrize("family", ["chart.rs", "chart.market.regime"])
def test_raw_close_identity_has_numpy_pandas_versions_without_indicator_preparation(family):
    from importlib.metadata import version

    stock = scope_for(
        bars(np.linspace(100, 110, 221)), feature_version="LEGACY_FEATURE_AD880AF"
    ).primary
    market = scope_for(
        bars([100.0] * 221), feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF"
    ).primary
    scope = CalculationScope(stock, {"market": market})
    assert api().legacy_fact_values(scope, family=family)
    identity = api().legacy_fact_provider_identity(scope, family=family)
    assert identity["preparation"] is None
    assert identity["calculation"] == {
        "backend": "pandas/raw-close",
        "packages": {name: version(name) for name in ("pandas", "numpy")},
    }
    for provider in identity["providers"].values():
        assert provider["backend"] == "pandas/raw-close"
        assert "pandas-ta" not in provider["packages"]


def test_63_bar_bias_agreement_is_descriptive_and_legacy_string_bonus_stays_false():
    from src.tools.technical.components.divergence import analyze_divergence

    index = np.arange(63)
    frame = bars(100 + 5 * np.sin(index / 3) + index / 10)
    frame["RSI"] = frame["cRSI"] = 50 + 20 * np.sin(index / 3) - index / 10
    result = facts(frame, "legacy.divergence")
    original = analyze_divergence(frame)
    assert result["rsi_crsi_bias_agreement"] is True
    assert result["rsi_bearish"]["bias"] == result["crsi"]["bias"] == "bearish"
    assert original.score == -25
    assert original.signals == ["약세 다이버전스 (Bearish Divergence)", "cRSI 약세 다이버전스"]
    crsi_signal = original.signals[1]
    legacy_bonus_predicate = bool(
        (result["rsi_bearish"] and "bearish" in crsi_signal.lower())
        or (result["rsi_bullish"] and "bullish" in crsi_signal.lower())
    )
    assert legacy_bonus_predicate is False
