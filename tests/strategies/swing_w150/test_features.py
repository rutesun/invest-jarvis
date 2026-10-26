"""Raw OHLCV to SWING_W150 feature boundary."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.strategies.models import BarFinality
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.technical.scorecard_models import DataStatus


def _raw_ohlcv() -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=260, freq="B")
    close = 100 + np.arange(260) * 0.15 + np.sin(np.arange(260) / 4)
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 100_000 + np.arange(260) * 100,
        },
        index=dates,
    )


def test_feature_builder_calculates_all_signal_inputs():
    from src.strategies.swing_w150.features import build_swing_features

    raw = _raw_ohlcv()
    features = build_swing_features(raw, SwingW150Parameters())

    required = {
        "SMA_20",
        "SMA_50",
        "SMA_150",
        "SMA_200",
        "ATR",
        "SuperTrend_Up",
        "SuperTrend_Dir",
        "cRSI",
        "MACD",
        "SMA_50_Slope_21",
        "SMA_150_Slope_21",
        "SMA_200_Slope_21",
        "Higher_Low",
        "Lower_Low_Lower_High",
        "Trend_Breakout_High_Prev",
        "Deep_Recovery_High_Prev",
    }
    assert required <= set(features.frame.columns)
    assert features.data_status is DataStatus.COMPLETE
    for period in (50, 150, 200):
        column = f"SMA_{period}"
        assert features.frame[f"{column}_Slope_21"].iloc[-1] == (
            features.frame[column].iloc[-1] - features.frame[column].iloc[-22]
        )
    assert list(raw.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_feature_builder_requires_only_minimum_history():
    from src.strategies.swing_w150.features import build_swing_features

    raw = _raw_ohlcv()
    params = SwingW150Parameters()

    assert build_swing_features(raw.tail(250), params).data_status is DataStatus.COMPLETE
    assert build_swing_features(raw.tail(249), params).data_status is DataStatus.INSUFFICIENT_DATA


def test_omitted_finalities_default_every_bar_to_final():
    raw = _raw_ohlcv()

    features = build_swing_features(raw, SwingW150Parameters())

    assert features.finalities == (BarFinality.FINAL,) * len(raw)


def test_explicit_finalities_reach_detector_input_in_bar_order():
    raw = _raw_ohlcv()
    finalities = (BarFinality.FINAL,) * (len(raw) - 1) + (BarFinality.PROVISIONAL,)

    features = build_swing_features(raw, SwingW150Parameters(), finalities=finalities)

    assert features.finalities == finalities
    assert features.frame.index.equals(raw.index)


def test_finality_count_must_match_raw_bar_count():
    raw = _raw_ohlcv()

    with pytest.raises(ValueError, match="finalities.*length"):
        build_swing_features(
            raw, SwingW150Parameters(), finalities=(BarFinality.FINAL,) * (len(raw) - 1)
        )


def test_insufficient_history_retains_aligned_finalities():
    raw = _raw_ohlcv().tail(249)
    finalities = (BarFinality.FINAL,) * 248 + (BarFinality.PROVISIONAL,)

    features = build_swing_features(raw, SwingW150Parameters(), finalities=finalities)

    assert features.data_status is DataStatus.INSUFFICIENT_DATA
    assert features.finalities == finalities
    assert features.frame.index.equals(raw.index)


@pytest.mark.parametrize(
    ("highs", "lows", "expected_column"),
    [
        (
            [10, 9, 8, 7, 6, 7, 8, 9, 10, 9, 7, 8, 9, 10, 11, 12],
            [9, 8, 7, 6, 5, 6, 7, 8, 9, 8, 6, 7, 8, 9, 10, 11],
            "Higher_Low",
        ),
        (
            [7, 8, 9, 10, 9, 8, 7, 6, 7, 8, 8.5, 9, 8, 7, 6, 5, 6, 7, 8, 9],
            [6, 7, 8, 9, 8, 7, 6, 5, 6, 7, 7.5, 8, 7, 6, 5, 4, 5, 6, 7, 8],
            "Lower_Low_Lower_High",
        ),
    ],
)
def test_confirmed_pivot_features_are_unchanged_by_future_suffix(highs, lows, expected_column):
    raw = _raw_ohlcv()
    tail_index = raw.index[250 - len(highs) : 250]
    raw.loc[tail_index, "High"] = highs
    raw.loc[tail_index, "Low"] = lows
    raw.loc[tail_index, "Close"] = (np.array(highs) + np.array(lows)) / 2
    raw.loc[tail_index, "Open"] = raw.loc[tail_index, "Close"]

    prefix = build_swing_features(raw.iloc[:250], SwingW150Parameters()).frame
    with_future = build_swing_features(raw, SwingW150Parameters()).frame

    for column in ("Higher_Low", "Lower_Low_Lower_High"):
        pd.testing.assert_series_equal(prefix[column], with_future[column].iloc[:250])
    assert bool(prefix[expected_column].iloc[-1]) is True


def test_default_breakout_thresholds_match_existing_fifty_and_twenty_bar_columns():
    features = build_swing_features(_raw_ohlcv(), SwingW150Parameters()).frame

    pd.testing.assert_series_equal(
        features["Trend_Breakout_High_Prev"], features["High_50_Prev"], check_names=False
    )
    pd.testing.assert_series_equal(
        features["Deep_Recovery_High_Prev"], features["High_20_Prev"], check_names=False
    )


def test_custom_breakout_lookbacks_use_previous_seven_and_five_bar_highs():
    raw = _raw_ohlcv()
    raw["High"] = 150.0
    for offset, high in [
        (-45, 250.0),
        (-15, 230.0),
        (-7, 190.0),
        (-6, 180.0),
        (-2, 175.0),
        (-1, 300.0),
    ]:
        raw.loc[raw.index[offset], "High"] = high
    custom = replace(
        SwingW150Parameters(), trend_breakout_lookback=7, deep_recovery_breakout_lookback=5
    )

    features = build_swing_features(raw, custom).frame

    assert features["Trend_Breakout_High_Prev"].iloc[-1] == 190.0
    assert features["Deep_Recovery_High_Prev"].iloc[-1] == 180.0
    assert features["High_50_Prev"].iloc[-1] == 250.0
    assert features["High_20_Prev"].iloc[-1] == 230.0
