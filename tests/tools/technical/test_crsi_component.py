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


@pytest.mark.parametrize(
    ("previous", "current", "signal_type", "bias", "intent", "entry_eligible"),
    [
        (10, 30, "pullback", "bullish", "entry", True),
        (90, 70, "overextension", "bearish", "risk", False),
    ],
)
def test_crsi_hook_signal_metadata(
    previous, current, signal_type, bias, intent, entry_eligible
):
    df = pd.DataFrame(
        {
            "cRSI": [previous, current],
            "cRSI_HighBand": [80, 80],
            "cRSI_LowBand": [20, 20],
        }
    )

    result = analyze_crsi(df)

    assert result.signal_metadata
    assert result.signal_metadata[0].source == "crsi"
    assert result.signal_metadata[0].signal_type == signal_type
    assert result.signal_metadata[0].bias == bias
    assert result.signal_metadata[0].intent == intent
    assert result.signal_metadata[0].severity == "medium"
    assert result.signal_metadata[0].entry_eligible is entry_eligible
