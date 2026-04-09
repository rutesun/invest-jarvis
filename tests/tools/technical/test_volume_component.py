import pytest
import pandas as pd
import numpy as np
from src.tools.technical.components.volume import analyze_volume
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def volume_spike_df():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.3
    volume = [1000000] * 99 + [5000000]  # spike on last day
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": volume,
    }, index=dates)
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_volume_spike(volume_spike_df):
    result = analyze_volume(volume_spike_df)
    assert any("급증" in s for s in result.signals)
    assert result.metrics.get("vol_ratio", 0) > 2.0


def test_volume_no_data():
    df = pd.DataFrame({"Close": [100], "Volume": [1000]})
    result = analyze_volume(df)
    assert result.score == 0
