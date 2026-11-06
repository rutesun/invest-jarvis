"""Strict formulas and explicit legacy provider ownership (no consumer scores)."""

from importlib import import_module

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.chart_analysis.models import CalculationScope, InputManifest, SeriesInput


def scope_for(frame, *, finality=None, feature_version="CHART_FEATURE_V1", coverage=None):
    manifest = InputManifest(
        ticker="TEST",
        exchange="XNYS",
        as_of=frame.index[-1].date(),
        origin="fixed-test-origin",
        input_profile="CHART_INPUT_V1",
        feature_version=feature_version,
        input_hash="",
        adjustment_policy="ADJUSTED",
        calendar_version="TEST_CAL_V1",
        finality=finality or "FINAL",
        coverage=coverage or {"complete": True},
    )
    return CalculationScope(SeriesInput(manifest, frame), {})


def bars(closes):
    close = np.asarray(closes, dtype=np.float64)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": np.full(len(close), 10.0),
        },
        index=pd.bdate_range("2025-01-01", periods=len(close)),
    )


def features(frame, **kwargs):
    return import_module("src.tools.technical.chart_analysis.features").calculate_features(
        scope_for(frame, **kwargs)
    )


def latest(frame, **kwargs):
    return features(frame, **kwargs)[frame.index[-1].date()]


def test_atr_seed_and_wilder_update_have_fixed_origin():
    frame = bars([100.0] * 15)
    frame["High"] = 100 + np.arange(1, 16, dtype=np.float64) / 2
    frame["Low"] = 100 - np.arange(1, 16, dtype=np.float64) / 2
    result = features(frame)
    assert result[frame.index[12].date()]["ATR"].value is None
    assert result[frame.index[13].date()]["ATR"].value == 7.5
    assert result[frame.index[14].date()]["ATR"].value == (13 * 7.5 + 15) / 14
    assert result[frame.index[0].date()]["TR"].value == 1


@pytest.mark.parametrize(
    "closes,expected",
    [
        (list(range(100, 115)), 100),
        (list(range(115, 100, -1)), 0),
        ([100] * 15, 50),
    ],
)
def test_rsi_uses_fourteen_changes_not_fourteen_closes(closes, expected):
    frame = bars(closes)
    result = features(frame)
    short = result[frame.index[13].date()]["RSI"]
    assert short.value is None and "HISTORY_SHORT" in short.reasons
    assert result[frame.index[14].date()]["RSI"].value == expected


def test_rsi_seed_and_next_update_use_separate_wilder_gain_loss():
    closes = [100, 102, 101, 104, 102, 103, 102, 104, 103, 105, 104, 107, 105, 106, 105, 108]
    frame = bars(closes)
    result = features(frame)
    gains, losses = 14 / 14, 9 / 14
    assert result[frame.index[14].date()]["RSI"].value == pytest.approx(
        100 - 100 / (1 + gains / losses)
    )
    gains, losses = (13 * gains + 3) / 14, 13 * losses / 14
    assert result[frame.index[15].date()]["RSI"].value == pytest.approx(
        100 - 100 / (1 + gains / losses)
    )


def test_sma_minimum_and_missing_dependencies_are_feature_specific():
    frame = bars(list(range(100, 151)))
    result = features(frame)
    assert result[frame.index[48].date()]["SMA_50"].value is None
    assert result[frame.index[49].date()]["SMA_50"].value == 124.5
    frame.loc[frame.index[-1], "Volume"] = np.nan
    row = latest(frame)
    assert row["SMA_50"].value == 125.5
    assert row["ATR"].value is not None
    assert row["Up_Volume_20"].value is None
    assert "INPUT_MISSING" in row["Up_Volume_20"].reasons


@pytest.mark.parametrize("column", ["Close", "High", "Low"])
def test_recursive_features_never_reseed_after_missing_dependency(column):
    frame = bars(list(range(100, 165)))
    frame.loc[frame.index[20], column] = np.nan
    result = features(frame)
    assert result[frame.index[19].date()]["ATR"].value is not None
    assert latest(frame)["ATR"].value is None
    assert "INPUT_MISSING" in latest(frame)["ATR"].reasons
    if column == "Close":
        assert latest(frame)["RSI"].value is None
        assert latest(frame)["SMA_20"].value == 154.5
    else:
        assert latest(frame)["RSI"].value == 100


def test_quality_materials_include_disjoint_windows_lags_and_volume_sample():
    frame = bars(list(range(100, 320)))
    row = latest(frame)
    assert row["SMA_200"].value == 219.5
    assert row["SMA_200_Lag20"].value == 199.5
    assert row["High_20_New"].value == 320
    assert row["High_20_Prior"].value == 300
    assert row["Low_20_New"].value == 299
    assert row["Low_20_Prior"].value == 279
    for lag in (5, 20, 60):
        assert row[f"Close_Lag{lag}"].value == 319 - lag
    assert row["Up_Volume_20"].value == 200
    assert row["Down_Volume_20"].value == 0
    assert row["Flat_Volume_20"].value == 0
    assert row["Up_Days_20"].value == 20
    assert row["Directional_Sample_20"].value == 20
    assert row["Max_Directional_Volume_20"].value == 10
    assert row["Max_Directional_Share_20"].value == 0.05
    assert row["Valid_Final_Streak"].value == 220
    assert row["History_Bars"].value == 220
    assert row["History_Status"].status == "READY"


def test_volume_direction_is_previous_close_and_zero_volume_does_not_count():
    frame = bars(
        [100] + [value + 2 * block for block in range(4) for value in (101, 100, 100, 101, 102)]
    )
    frame.loc[frame.index[-1], "Volume"] = 0
    row = latest(frame)
    assert row["Up_Days_20"].value == 12
    assert row["Down_Days_20"].value == 4
    assert row["Flat_Days_20"].value == 4
    assert row["Directional_Sample_20"].value == 15
    assert row["Up_Volume_20"].value == 110
    assert row["Down_Volume_20"].value == 40
    assert row["Flat_Volume_20"].value == 40


def test_zero_atr_and_zero_direction_volume_are_raw_values_not_fake_scores():
    frame = bars([100] * 21)
    frame[["Open", "High", "Low", "Close"]] = 100.0
    row = latest(frame)
    assert row["ATR"].value == 0
    assert row["RSI"].value == 50
    assert row["Directional_Sample_20"].value == 0
    assert row["Max_Directional_Share_20"].value is None
    assert "ZERO_DIRECTIONAL_VOLUME" in row["Max_Directional_Share_20"].reasons
    assert not any("score" in key.lower() or "action" in key.lower() for key in row)


def test_price_and_volume_units_preserve_their_respective_materials():
    frame = bars(100 + np.arange(65) + np.sin(np.arange(65)))
    base = latest(frame)
    scaled = frame.copy()
    scaled[["Open", "High", "Low", "Close"]] *= 100
    scaled["Volume"] *= 10
    row = latest(scaled)
    for key in ("Close", "TR", "ATR", "SMA_50", "High_20_New", "Low_20_Prior", "Close_Lag60"):
        assert row[key].value == pytest.approx(100 * base[key].value)
    assert row["RSI"].value == pytest.approx(base["RSI"].value)
    assert row["Up_Volume_20"].value == 10 * base["Up_Volume_20"].value
    assert row["Directional_Sample_20"].value == base["Directional_Sample_20"].value
    assert row["Max_Directional_Share_20"].value == base["Max_Directional_Share_20"].value


def test_legacy_feature_selection_calculates_with_explicit_version_and_keeps_raw_hash():
    from src.tools.technical.indicators import IndicatorCalculator

    module = import_module("src.tools.technical.chart_analysis.legacy_features")
    frame = bars(list(range(100, 180)))
    scope = scope_for(frame, feature_version="LEGACY_FEATURE_AD880AF")
    before = scope.primary.manifest.input_hash
    expected = IndicatorCalculator().calculate(frame)
    pd.testing.assert_frame_equal(
        module.legacy_features_for_series(scope.primary), expected, check_exact=True
    )
    assert scope.primary.manifest.input_hash == before
    pd.testing.assert_frame_equal(scope.primary.raw, frame)


def test_trailing_preview_does_not_seed_final_and_intermediate_provisional_blocks_prefix():
    frame = bars(list(range(100, 116)))
    finality = {day.date(): "FINAL" for day in frame.index}
    finality[frame.index[13].date()] = "PROVISIONAL"
    result = features(frame, finality=finality)
    preview = result[frame.index[13].date()]["ATR"]
    assert preview.value == 2 and preview.status == "PROVISIONAL"
    assert "PROVISIONAL_PREVIEW" in preview.reasons
    after = result[frame.index[14].date()]["ATR"]
    assert after.value is None and "INCOMPLETE_PREFIX" in after.reasons
    assert result[frame.index[12].date()]["History_Status"].status == "READY"


def test_missing_session_stays_in_place_and_does_not_poison_earlier_prefix():
    frame = bars(list(range(100, 135)))
    frame.loc[frame.index[25], :] = np.nan
    finality = {day.date(): "FINAL" for day in frame.index}
    finality[frame.index[25].date()] = "UNKNOWN"
    result = features(
        frame,
        finality=finality,
        coverage={"complete": False, "missing_sessions": [frame.index[25].date()]},
    )
    assert len(result) == 35
    assert result[frame.index[24].date()]["ATR"].status == "READY"
    assert result[frame.index[26].date()]["ATR"].value is None
    assert "INCOMPLETE_PREFIX" in result[frame.index[26].date()]["ATR"].reasons


def test_absent_expected_session_is_reinserted_without_compressing_windows():
    frame = bars(list(range(100, 135)))
    missing_on = frame.index[25].date()
    result = features(
        frame.drop(frame.index[25]), coverage={"expected_sessions": tuple(frame.index.date)}
    )
    assert len(result) == 35
    assert result[missing_on]["Close"].value is None
    assert "INPUT_MISSING" in result[missing_on]["Close"].reasons
    assert result[frame.index[26].date()]["SMA_20"].value is None
    assert result[frame.index[24].date()]["ATR"].status == "READY"


def test_missing_origin_blocks_recursive_seed_but_preserves_independent_materials():
    frame = bars(list(range(100, 152)))
    row = latest(frame, coverage={"reached_start": False})
    assert row["Close"].value == 151
    assert row["SMA_50"].value == 126.5
    assert row["High_20_New"].value == 152
    for key in ("ATR", "RSI", "History_Status"):
        assert row[key].value is None
        assert "INCOMPLETE_PREFIX" in row[key].reasons


@pytest.mark.parametrize("count", [219, 220, 251, 252])
def test_calculation_and_publication_history_do_not_globally_block_materials(count):
    row = latest(bars(list(range(100, 100 + count))))
    assert row["Close"].value == 99 + count
    assert row["ATR"].value is not None
    assert row["SMA_200"].value is not None
    assert (row["SMA_200_Lag20"].value is not None) == (count >= 220)
    assert row["History_Bars"].value == count
    assert row["History_Status"].status == "READY"


@pytest.mark.parametrize(
    "missing_column,unaffected", [("High", "RSI"), ("Volume", "ATR"), ("Open", "SMA_20")]
)
def test_initial_missing_field_does_not_poison_unrelated_features(missing_column, unaffected):
    frame = bars(list(range(100, 131)))
    frame.loc[frame.index[0], missing_column] = np.nan
    row = latest(frame)
    assert row[unaffected].value is not None
    assert row["History_Status"].value is None


def test_strict_provider_rejects_legacy_version_and_ignores_unrelated_market():
    frame = bars(list(range(100, 120)))
    module = import_module("src.tools.technical.chart_analysis.features")
    with pytest.raises(ValueError, match="CHART_FEATURE_V1"):
        module.calculate_features(scope_for(frame, feature_version="LEGACY_FEATURE_AD880AF"))
    base = scope_for(frame)
    market = scope_for(frame, finality="UNKNOWN").primary
    assert module.calculate_features(
        CalculationScope(base.primary, {"market": market})
    ) == module.calculate_features(base)


@pytest.mark.parametrize(
    "column,value", [("Close", 0), ("High", np.inf), ("Volume", -1), ("Low", 1000)]
)
def test_invalid_numeric_inputs_are_explicit_errors(column, value):
    frame = bars([100, 101])
    frame.loc[frame.index[-1], column] = value
    with pytest.raises(ValueError):
        features(frame)


def test_legacy_shadow_is_a_separate_owner_and_matches_original_directly():
    from src.tools.technical.indicators import IndicatorCalculator

    module = import_module("src.tools.technical.chart_analysis.legacy_features")
    rng = np.random.default_rng(927)
    frame = bars(100 + np.cumsum(rng.normal(0, 1, 280)))
    pd.testing.assert_frame_equal(
        module.calculate_legacy_features(frame),
        IndicatorCalculator().calculate(frame),
        check_exact=True,
    )
    # The shadow must remain independent when the old public method is replaced.
    original = IndicatorCalculator.calculate
    try:
        IndicatorCalculator.calculate = lambda *_: (_ for _ in ()).throw(
            AssertionError("old owner called")
        )
        assert len(module.calculate_legacy_features(frame)) == 280
    finally:
        IndicatorCalculator.calculate = original


@pytest.mark.parametrize("kind", ["frozen", "middle_nan", "multiindex", "empty"])
def test_legacy_shadow_matches_original_on_compatibility_inputs(kind):
    from pathlib import Path

    from src.tools.technical.indicators import IndicatorCalculator

    module = import_module("src.tools.technical.chart_analysis.legacy_features")
    frame = pd.read_csv(
        Path(__file__).resolve().parents[3] / "fixtures/chart_analysis/seed_path.csv",
        index_col=0,
        parse_dates=True,
    )
    if kind == "middle_nan":
        frame.loc[frame.index[21], ["High", "Close", "Volume"]] = np.nan
    elif kind == "multiindex":
        frame.columns = pd.MultiIndex.from_product([frame.columns, ["TEST"]])
    elif kind == "empty":
        frame = frame.iloc[:0]
    pd.testing.assert_frame_equal(
        module.calculate_legacy_features(frame),
        IndicatorCalculator().calculate(frame),
        check_exact=True,
    )


def test_supplied_feature_provider_preserves_columns_and_never_recomputes():
    module = import_module("src.tools.technical.chart_analysis.legacy_features")
    frame = bars([100, 101, 102])
    frame["RSI"] = [8, 9, 10]
    supplied = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF").primary
    result = module.legacy_features_for_series(supplied)
    pd.testing.assert_frame_equal(result, frame)
    result.loc[frame.index[-1], "RSI"] = 999
    assert supplied.raw["RSI"].iloc[-1] == 10
    with pytest.raises(ValueError, match="legacy"):
        module.legacy_features_for_series(scope_for(frame).primary)


def test_provider_identity_identifies_real_packages_backend_and_supplied_profile():
    module = import_module("src.tools.technical.chart_analysis.features")
    strict = module.feature_provider_identity("CHART_FEATURE_V1")
    legacy = module.feature_provider_identity("LEGACY_FEATURE_AD880AF")
    supplied = module.feature_provider_identity("SUPPLIED_LEGACY_FEATURE_AD880AF")
    assert strict["feature_version"] == "CHART_FEATURE_V1"
    from importlib.metadata import version
    from importlib.util import find_spec

    assert legacy["packages"]["pandas-ta"] == version("pandas-ta")
    has_talib = find_spec("talib") is not None
    assert legacy["backend"] == ("pandas-ta/talib" if has_talib else "pandas-ta/native")
    assert legacy["talib_installed"] is has_talib
    assert strict["packages"] == {name: version(name) for name in ("numpy", "pandas")}
    assert supplied["backend"] == "supplied-columns"
    assert strict != legacy != supplied
    with pytest.raises(ValueError):
        module.feature_provider_identity("unknown")
