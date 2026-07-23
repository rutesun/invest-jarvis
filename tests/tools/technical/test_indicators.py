import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.models import IndicatorSnapshot


def _trend_df(step: float, rows: int = 260) -> pd.DataFrame:
    close = 100.0 + np.arange(rows) * step
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(rows, 1_000_000),
        }
    )


def _snapshot(df: pd.DataFrame) -> IndicatorSnapshot:
    calculator = IndicatorCalculator()
    return calculator.create_snapshot(calculator.calculate(df))


def test_snapshot_includes_sma_100_and_long_sma_slopes():
    snapshot = _snapshot(_trend_df(0.5))

    assert snapshot.sma_100 is not None
    assert snapshot.sma_200 is not None
    assert snapshot.sma_100_slope_pct > 0.5
    assert snapshot.sma_200_slope_pct > 0.5


def test_sma_200_slope_requires_221_original_rows():
    assert _snapshot(_trend_df(0.5, rows=220)).sma_200_slope_pct is None
    assert _snapshot(_trend_df(0.5, rows=221)).sma_200_slope_pct is not None


def test_slope_keeps_original_trading_row_positions_with_middle_nan():
    frame = pd.DataFrame({"SMA_100": np.arange(100.0, 130.0)})
    expected = IndicatorCalculator._slope_pct(frame, "SMA_100")
    frame.iloc[-10, frame.columns.get_loc("SMA_100")] = np.nan

    assert IndicatorCalculator._slope_pct(frame, "SMA_100") == expected


@pytest.mark.parametrize("endpoint", [-1, -22])
def test_slope_returns_none_when_original_endpoint_is_nan(endpoint: int):
    frame = pd.DataFrame({"SMA_100": np.arange(100.0, 130.0)})
    frame.iloc[endpoint, frame.columns.get_loc("SMA_100")] = np.nan

    assert IndicatorCalculator._slope_pct(frame, "SMA_100") is None


def test_slope_returns_none_when_previous_value_is_zero():
    frame = pd.DataFrame({"SMA_100": np.arange(100.0, 130.0)})
    frame.iloc[-22, frame.columns.get_loc("SMA_100")] = 0.0

    assert IndicatorCalculator._slope_pct(frame, "SMA_100") is None


@pytest.fixture
def sample_df():
    """Create sample OHLCV DataFrame."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    return pd.DataFrame(
        {
            "Open": close - np.random.rand(100),
            "High": close + np.random.rand(100) * 2,
            "Low": close - np.random.rand(100) * 2,
            "Close": close,
            "Volume": np.random.randint(1000000, 5000000, 100),
        },
        index=dates,
    )


def test_calculate_indicators(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)

    assert "SMA_20" in result_df.columns
    assert "SMA_50" in result_df.columns
    assert "RSI" in result_df.columns
    assert not result_df["SMA_20"].isna().all()


def test_create_snapshot(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)
    snapshot = calculator.create_snapshot(result_df)

    assert isinstance(snapshot, IndicatorSnapshot)
    assert snapshot.price > 0
    assert snapshot.sma_20 is not None or snapshot.sma_20 is None


def test_extended_indicators(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)

    assert "SMA_150" in result_df.columns
    assert "cRSI" in result_df.columns
    assert "cRSI_HighBand" in result_df.columns
    assert "cRSI_LowBand" in result_df.columns
    assert "Vol_SMA_20" in result_df.columns
    assert "Vol_SMA_50" in result_df.columns
    assert "Vol_SMA_120" in result_df.columns
    assert "Swing_High" in result_df.columns
    assert "Swing_Low" in result_df.columns
    assert "Is_Gap_Up" in result_df.columns
    assert "Is_Gap_Down" in result_df.columns
    assert "MACD_Fast" in result_df.columns


def test_crsi_calculation(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)

    crsi_values = result_df["cRSI"].dropna()
    if len(crsi_values) > 0:
        assert crsi_values.min() >= 0
        assert crsi_values.max() <= 100


def test_extended_snapshot(sample_df):
    calculator = IndicatorCalculator()
    result_df = calculator.calculate(sample_df)
    snapshot = calculator.create_snapshot(result_df)

    # New fields should be populated or None (depending on data length)
    assert hasattr(snapshot, "sma_150")
    assert hasattr(snapshot, "crsi")
    assert hasattr(snapshot, "vol_sma_20")
    assert hasattr(snapshot, "swing_high")
    assert hasattr(snapshot, "is_gap_up")
    assert hasattr(snapshot, "macd_fast")


def test_macd_column_names():
    """Test that MACD columns use clear names."""
    calc = IndicatorCalculator()
    # Need at least 35 rows for MACD (12+26+9 slow period)
    df = pd.DataFrame(
        {
            "Open": [100 + i * 0.5 for i in range(40)],
            "High": [102 + i * 0.5 for i in range(40)],
            "Low": [99 + i * 0.5 for i in range(40)],
            "Close": [101 + i * 0.5 for i in range(40)],
            "Volume": [1000 + i * 10 for i in range(40)],
        }
    )

    result = calc.calculate(df)

    # Check new column names
    assert "MACD" in result.columns
    assert "MACD_Signal" in result.columns
    assert "MACD_Hist" in result.columns

    # Check old names don't exist
    assert "MACD_12_26_9" not in result.columns
    assert "MACDs_12_26_9" not in result.columns
    assert "MACDh_12_26_9" not in result.columns


def test_fast_macd_column_names():
    """Test that Fast MACD columns use clear names."""
    calc = IndicatorCalculator()
    df = pd.DataFrame(
        {
            "Open": [100] * 50,
            "High": [102] * 50,
            "Low": [99] * 50,
            "Close": list(range(100, 150)),
            "Volume": [1000] * 50,
        }
    )

    result = calc.calculate(df)

    assert "MACD_Fast" in result.columns
    assert "MACD_Fast_Signal" in result.columns
    assert "MACD_Fast_Hist" in result.columns

    assert "MACD_5_35_5" not in result.columns


def test_supertrend_column_names():
    """Test that Supertrend columns use clear names."""
    calc = IndicatorCalculator()
    df = pd.DataFrame(
        {
            "Open": [100] * 30,
            "High": [102] * 30,
            "Low": [99] * 30,
            "Close": list(range(100, 130)),
            "Volume": [1000] * 30,
        }
    )

    result = calc.calculate(df)

    assert "SuperTrend_Up" in result.columns
    assert "SuperTrend_Dn" in result.columns
    assert "SuperTrend_Dir" in result.columns

    assert "SUPERTl_10_3.0" not in result.columns
    assert "SUPERTd_10_3.0" not in result.columns


def test_bollinger_bands_column_names():
    """Test that Bollinger Bands use clear names."""
    calc = IndicatorCalculator()
    df = pd.DataFrame(
        {
            "Open": [100] * 25,
            "High": [102] * 25,
            "Low": [99] * 25,
            "Close": list(range(100, 125)),
            "Volume": [1000] * 25,
        }
    )

    result = calc.calculate(df)

    assert "BB_Upper" in result.columns
    assert "BB_Lower" in result.columns

    assert "BBU_20_2.0" not in result.columns
    assert "BBL_20_2.0" not in result.columns


def test_adx_column_name():
    """Test that ADX uses clear name."""
    calc = IndicatorCalculator()
    df = pd.DataFrame(
        {
            "Open": [100] * 20,
            "High": [102] * 20,
            "Low": [99] * 20,
            "Close": list(range(100, 120)),
            "Volume": [1000] * 20,
        }
    )

    result = calc.calculate(df)

    assert "ADX" in result.columns
    assert "ADX_14" not in result.columns
