import numpy as np
import pandas as pd
import pytest

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
        close[i - 5 : i + 5] += np.linspace(0, 3, 10)

    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1000000] * 100,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    return calculator.calculate(df)


@pytest.fixture
def bearish_divergence_df():
    """Create DataFrame with bearish divergence (price up, RSI down)."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")

    # Price: uptrend with higher highs
    close = 100 + np.arange(100) * 0.3

    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1000000] * 100,
        },
        index=dates,
    )

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
    df = pd.DataFrame(
        {
            "Close": [100, 101, 102],
            "RSI": [50, 51, 52],
        }
    )

    result = analyze_divergence(df)
    assert result.score == 0
    assert "데이터 부족" in result.evidence[0]


def test_divergence_metrics(bullish_divergence_df):
    """Test metrics are populated."""
    result = analyze_divergence(bullish_divergence_df)

    # Should have some metrics
    assert isinstance(result.metrics, dict)


@pytest.mark.parametrize(
    ("price_values", "rsi_values", "bias", "intent"),
    [
        ((100, 90, 80), (50, 20, 30), "bullish", "watch"),
        ((100, 110, 120), (50, 80, 70), "bearish", "risk"),
    ],
)
def test_divergence_signal_metadata(price_values, rsi_values, bias, intent):
    close = np.full(60, price_values[0], dtype=float)
    rsi = np.full(60, rsi_values[0], dtype=float)
    for index, price, rsi_value in zip((40, 55), price_values[1:], rsi_values[1:], strict=True):
        close[index] = price
        rsi[index] = rsi_value

    result = analyze_divergence(pd.DataFrame({"Close": close, "RSI": rsi}))

    metadata = next(item for item in result.signal_metadata if item.bias == bias)
    assert metadata.source == "divergence"
    assert metadata.signal_type == "reversal"
    assert metadata.intent == intent
    assert metadata.severity == "medium"
    assert metadata.entry_eligible is False
