import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.strategies.risk import RiskStrategy


@pytest.fixture
def sample_df():
    dates = pd.date_range("2023-01-01", periods=300, freq="D")
    close = 100 + np.cumsum(np.random.randn(300) * 2)
    df = pd.DataFrame(
        {
            "Open": close - np.random.rand(300),
            "High": close + np.random.rand(300) * 3,
            "Low": close - np.random.rand(300) * 3,
            "Close": close,
            "Volume": np.random.randint(1000000, 5000000, 300),
        },
        index=dates,
    )
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_risk_strategy(sample_df):
    strategy = RiskStrategy()
    result = strategy.analyze(sample_df)

    assert result.name == "risk"
    assert result.status in ["고위험", "중위험", "저위험"]
    assert isinstance(result.confidence, float)
    assert len(result.metrics) > 0
