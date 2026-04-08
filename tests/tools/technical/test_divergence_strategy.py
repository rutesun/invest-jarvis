import pytest
import pandas as pd
import numpy as np
from src.tools.technical.strategies.divergence import DivergenceStrategy
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def sample_df():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    df = pd.DataFrame({
        "Open": close - np.random.rand(100),
        "High": close + np.random.rand(100) * 2,
        "Low": close - np.random.rand(100) * 2,
        "Close": close,
        "Volume": np.random.randint(1000000, 5000000, 100),
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_divergence_strategy(sample_df):
    strategy = DivergenceStrategy()
    result = strategy.analyze(sample_df)

    assert result.name == "divergence"
    assert result.status in ["강세", "약세", "중립"]
    assert isinstance(result.confidence, float)
