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


@pytest.mark.parametrize(
    ("close", "expected_signal", "signal_type", "bias", "intent", "severity"),
    [
        (
            np.concatenate([np.full(202, 200.0), np.linspace(100.0, 160.0, 50)]),
            "강세",
            "trend",
            "bullish",
            "watch",
            "low",
        ),
        (
            np.concatenate([np.full(202, 200.0), np.full(50, 100.0)]),
            "약세/보합",
            "breakdown",
            "bearish",
            "risk",
            "medium",
        ),
    ],
)
def test_minervini_non_stage2_signal_metadata(
    close, expected_signal, signal_type, bias, intent, severity
):
    dates = pd.date_range("2024-01-01", periods=len(close), freq="D")
    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1_000_000] * len(close),
        },
        index=dates,
    )

    result = analyze_minervini(IndicatorCalculator().calculate(df))

    assert expected_signal in result.signals[0]
    metadata = result.signal_metadata[0]
    assert metadata.source == "minervini"
    assert metadata.signal_type == signal_type
    assert metadata.bias == bias
    assert metadata.intent == intent
    assert metadata.severity == severity
    assert metadata.entry_eligible is False


def test_minervini_insufficient_data():
    df = pd.DataFrame({"Close": [100, 101, 102]})
    result = analyze_minervini(df)
    assert result.score == 0
    assert "데이터 부족" in result.evidence[0]
