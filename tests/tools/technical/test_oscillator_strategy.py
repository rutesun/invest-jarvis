import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.strategies.oscillator import OscillatorStrategy


@pytest.fixture
def overbought_df():
    """Create DataFrame with overbought conditions."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.8  # strong uptrend
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


def test_oscillator_strategy_overbought(overbought_df):
    strategy = OscillatorStrategy()
    result = strategy.analyze(overbought_df)

    assert result.name == "oscillator"
    assert result.status in ["과매수", "약과매수"]
    assert len(result.evidence) > 0
    assert len(result.metrics) > 0
    assert "rsi" in result.metrics
