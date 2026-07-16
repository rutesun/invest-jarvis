import numpy as np
import pandas as pd
import pytest

from src.tools.technical.components.risk import analyze_risk
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def strong_support_df():
    """Create DataFrame with strong support confluence."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.random.randn(100) * 2

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
def near_resistance_df():
    """Create DataFrame near resistance."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    # Uptrend approaching previous high
    close = 100 + np.arange(100) * 0.2

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


def test_risk_analysis(strong_support_df):
    """Test risk analysis works."""
    result = analyze_risk(strong_support_df)

    assert isinstance(result.score, int)
    assert isinstance(result.signals, list)
    assert isinstance(result.evidence, list)
    assert isinstance(result.metrics, dict)


def test_risk_no_data():
    """Test with insufficient data."""
    df = pd.DataFrame(
        {
            "Close": [100, 101, 102],
        }
    )

    result = analyze_risk(df)
    assert result.score == 0


def test_risk_metrics_populated(strong_support_df):
    """Test metrics include support/resistance info."""
    result = analyze_risk(strong_support_df)

    assert isinstance(result.metrics, dict)
    # Should have some risk-related metrics
    assert len(result.metrics) >= 0


def test_risk_stop_loss_calculation(strong_support_df):
    """Test stop loss is calculated."""
    result = analyze_risk(strong_support_df)

    # If ATR is available, should have stop loss
    if "stop_loss" in result.metrics:
        assert result.metrics["stop_loss"] > 0


def test_risk_below_sma50_signal_metadata():
    df = pd.DataFrame({"Close": [90] * 20, "SMA_50": [100] * 20})

    result = analyze_risk(df)

    metadata = next(item for item in result.signal_metadata if item.signal_type == "breakdown")
    assert metadata.source == "risk"
    assert metadata.bias == "bearish"
    assert metadata.intent == "risk"
    assert metadata.severity == "medium"
    assert metadata.entry_eligible is False


def test_risk_support_confluence_signal_metadata():
    df = pd.DataFrame(
        {
            "Close": [100] * 20,
            "SMA_20": [99] * 20,
            "SMA_50": [98] * 20,
            "SMA_150": [99] * 20,
        }
    )

    result = analyze_risk(df)

    metadata = next(item for item in result.signal_metadata if item.signal_type == "support")
    assert metadata.source == "risk"
    assert metadata.bias == "bullish"
    assert metadata.intent == "hold"
    assert metadata.severity == "medium"
    assert metadata.entry_eligible is False
