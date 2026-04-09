import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.supertrend import analyze_supertrend
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def uptrend_df():
    """DataFrame with supertrend uptrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.5
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
def downtrend_df():
    """DataFrame with supertrend downtrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 150 - np.arange(100) * 0.5
    df = pd.DataFrame({
        "Open": close + 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_supertrend_uptrend(uptrend_df):
    """Test supertrend detects uptrend."""
    result = analyze_supertrend(uptrend_df)

    assert result.score > 0
    assert any("상승" in sig or "매수" in sig for sig in result.signals)
    assert "supertrend_direction" in result.metrics


def test_supertrend_downtrend(downtrend_df):
    """Test supertrend detects downtrend."""
    result = analyze_supertrend(downtrend_df)

    assert result.score < 0
    assert any("하락" in sig or "매도" in sig for sig in result.signals)
    assert result.metrics["supertrend_direction"] == -1


def test_supertrend_direction_change():
    """Test supertrend direction change detection."""
    # Create data with direction change
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    close = [100 - i * 0.5 for i in range(25)] + [87.5 + i * 0.5 for i in range(25)]
    df = pd.DataFrame({
        "Open": [c - 0.5 for c in close],
        "High": [c + 1 for c in close],
        "Low": [c - 1 for c in close],
        "Close": close,
        "Volume": [1000000] * 50,
    }, index=dates)

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_supertrend(df)

    # Should detect current trend
    assert isinstance(result.score, int)
    assert "supertrend_direction" in result.metrics


def test_supertrend_no_data():
    """Test with insufficient data."""
    df = pd.DataFrame({
        "Close": [100],
        "High": [101],
        "Low": [99],
    })

    result = analyze_supertrend(df)

    assert result.score == 0
    assert len(result.signals) == 0


def test_supertrend_with_real_calculation():
    """Test with actual supertrend calculation."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(100) * 2)

    df = pd.DataFrame({
        "Open": close - np.random.rand(100),
        "High": close + np.random.rand(100) * 2,
        "Low": close - np.random.rand(100) * 2,
        "Close": close,
        "Volume": np.random.randint(1000000, 5000000, 100),
    }, index=dates)

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_supertrend(df)

    # Should produce valid result
    assert isinstance(result.score, int)
    assert isinstance(result.signals, list)
    assert isinstance(result.evidence, list)
    assert isinstance(result.metrics, dict)
