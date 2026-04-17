import numpy as np
import pandas as pd
import pytest

from src.tools.technical.components.crsi import analyze_crsi
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def sample_df():
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    df = pd.DataFrame(
        {
            "Open": close - np.random.rand(100),
            "High": close + np.random.rand(100) * 2,
            "Low": close - np.random.rand(100) * 2,
            "Close": close,
            "Volume": np.random.randint(1000000, 5000000, 100),
        },
        index=dates,
    )
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_crsi_analysis(sample_df):
    result = analyze_crsi(sample_df)
    assert isinstance(result.score, int)
    assert "crsi" in result.metrics or len(result.evidence) > 0


def test_crsi_no_data():
    df = pd.DataFrame({"Close": [100]})
    result = analyze_crsi(df)
    assert result.score == 0
