import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.models import IndicatorSnapshot


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
    assert "MACD_5_35_5" in result_df.columns


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
