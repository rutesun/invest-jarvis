import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.strategies.disparity import DisparityStrategy


@pytest.fixture
def sample_df():
    dates = pd.date_range("2024-01-01", periods=150, freq="D")
    close = 100 + np.cumsum(np.random.randn(150) * 1)
    df = pd.DataFrame(
        {
            "Open": close - np.random.rand(150),
            "High": close + np.random.rand(150) * 2,
            "Low": close - np.random.rand(150) * 2,
            "Close": close,
            "Volume": np.random.randint(1000000, 5000000, 150),
        },
        index=dates,
    )
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_disparity_strategy(sample_df):
    strategy = DisparityStrategy()
    result = strategy.analyze(sample_df)

    assert result.name == "disparity"
    assert result.status in ["과열", "침체", "중립"]
    assert isinstance(result.confidence, float)
    assert len(result.metrics) > 0
