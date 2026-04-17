import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.strategies.trend import TrendStrategy


@pytest.fixture
def uptrend_df():
    """Create DataFrame with clear uptrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.5  # steady uptrend
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
def downtrend_df():
    """Create DataFrame with clear downtrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 150 - np.arange(100) * 0.5  # steady downtrend
    df = pd.DataFrame(
        {
            "Open": close + 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1000000] * 100,
        },
        index=dates,
    )
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_trend_strategy_uptrend(uptrend_df):
    strategy = TrendStrategy()
    result = strategy.analyze(uptrend_df)

    assert result.name == "trend"
    assert result.status == "강세"
    assert result.confidence > 50


def test_trend_strategy_downtrend(downtrend_df):
    strategy = TrendStrategy()
    result = strategy.analyze(downtrend_df)

    assert result.name == "trend"
    assert result.status == "약세"


def test_trend_strategy_has_evidence(uptrend_df):
    strategy = TrendStrategy()
    result = strategy.analyze(uptrend_df)

    assert len(result.evidence) > 0
    assert len(result.metrics) > 0
