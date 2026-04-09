import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.divergence import analyze_divergence
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def bullish_divergence_df():
    """Create DataFrame with bullish divergence (price down, RSI up)."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")

    # Price: downtrend with lower lows
    close = 100 - np.arange(100) * 0.3

    # Add some noise to create peaks
    for i in [20, 50, 80]:
        close[i-5:i+5] += np.linspace(0, 3, 10)

    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)

    calculator = IndicatorCalculator()
    return calculator.calculate(df)


@pytest.fixture
def bearish_divergence_df():
    """Create DataFrame with bearish divergence (price up, RSI down)."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")

    # Price: uptrend with higher highs
    close = 100 + np.arange(100) * 0.3

    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)

    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_divergence_analysis(bullish_divergence_df):
    """Test divergence detection works."""
    result = analyze_divergence(bullish_divergence_df)

    assert isinstance(result.score, int)
    assert isinstance(result.signals, list)
    assert isinstance(result.evidence, list)
    assert isinstance(result.metrics, dict)


def test_divergence_no_data():
    """Test with insufficient data."""
    df = pd.DataFrame({
        "Close": [100, 101, 102],
        "RSI": [50, 51, 52],
    })

    result = analyze_divergence(df)
    assert result.score == 0
    assert "데이터 부족" in result.evidence[0]


def test_divergence_metrics(bullish_divergence_df):
    """Test metrics are populated."""
    result = analyze_divergence(bullish_divergence_df)

    # Should have some metrics
    assert isinstance(result.metrics, dict)
