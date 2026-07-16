import numpy as np
import pandas as pd
import pytest

from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def stage2_df():
    """Create DataFrame meeting all Stage 2 conditions."""
    dates = pd.date_range("2024-01-01", periods=252, freq="D")
    # Steady uptrend from 100 to 200
    close = 100 + np.arange(252) * 0.4
    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1000000] * 252,
        },
        index=dates,
    )
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_minervini_stage2(stage2_df):
    result = analyze_minervini(stage2_df)
    assert result.score == 40
    assert "Stage 2" in result.signals[0]
    assert result.signal_metadata[0].source == "minervini"
    assert result.signal_metadata[0].signal_type == "trend"
    assert result.signal_metadata[0].intent == "hold"
    assert result.signal_metadata[0].entry_eligible is True


def test_minervini_insufficient_data():
    df = pd.DataFrame({"Close": [100, 101, 102]})
    result = analyze_minervini(df)
    assert result.score == 0
    assert "데이터 부족" in result.evidence[0]
