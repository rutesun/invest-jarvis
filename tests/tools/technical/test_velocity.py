import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.velocity import analyze_velocity
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def accelerating_df():
    """Create DataFrame with accelerating uptrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    # Accelerating: slope increases over time
    close = 100 + np.cumsum(np.linspace(0.1, 1.0, 100))
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_velocity_accelerating(accelerating_df):
    result = analyze_velocity(accelerating_df)
    assert result.score > 0
    assert "norm_slope" in result.metrics


def test_velocity_insufficient_data():
    df = pd.DataFrame({"Close": [100, 101], "SMA_20": [100, 101]})
    result = analyze_velocity(df)
    assert result.score == 0
