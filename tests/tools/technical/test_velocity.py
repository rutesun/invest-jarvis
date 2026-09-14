import numpy as np
import pandas as pd
import pytest

from src.tools.technical.components.velocity import analyze_velocity
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def accelerating_df():
    """Create DataFrame with accelerating uptrend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    # Accelerating: slope increases over time
    close = 100 + np.cumsum(np.linspace(0.1, 1.0, 100))
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


def test_velocity_accelerating(accelerating_df):
    result = analyze_velocity(accelerating_df)
    assert result.score > 0
    assert "norm_slope" in result.metrics


def test_velocity_insufficient_data():
    df = pd.DataFrame({"Close": [100, 101], "SMA_20": [100, 101]})
    result = analyze_velocity(df)
    assert result.score == 0


@pytest.mark.parametrize(
    ("sma_20", "signal_type", "bias", "intent"),
    [
        (
            [100, 100, 100, 100, 100, 100, 99, 98, 97, 96, 96, 97, 98, 99, 100],
            "trend",
            "bullish",
            "hold",
        ),
        (
            [100, 100, 100, 100, 100, 100, 101, 102, 103, 104, 104, 103, 102, 101, 100],
            "breakdown",
            "bearish",
            "risk",
        ),
    ],
)
def test_velocity_turn_signal_metadata(sma_20, signal_type, bias, intent):
    result = analyze_velocity(pd.DataFrame({"SMA_20": sma_20}))

    assert result.signal_metadata
    metadata = result.signal_metadata[0]
    assert metadata.source == "velocity"
    assert metadata.signal_type == signal_type
    assert metadata.bias == bias
    assert metadata.intent == intent
    assert metadata.severity == "medium"
    assert metadata.entry_eligible is False


# SMA20 기울기가 아직 하락(전환점 down)인 시계열. 가드 검증에 재사용.
_SMA20_TURN_DOWN = [100] * 6 + [101, 102, 103, 104, 104, 103, 102, 101, 100]


def test_velocity_suppresses_down_penalty_when_price_reclaimed_sma20():
    # 종가가 이미 SMA20(최근값 100) 위(106)면 SMA20 기울기 하락은 지연(lag) 아티팩트.
    # '하락 가속/전환점' 벌점을 억제해 반등 초입을 역방향으로 때리지 않는다.
    df = pd.DataFrame({"SMA_20": _SMA20_TURN_DOWN, "Close": [106] * len(_SMA20_TURN_DOWN)})

    result = analyze_velocity(df)

    assert result.score >= -5, f"lag 벌점 억제 실패: score={result.score}"
    assert not any(m.bias == "bearish" for m in result.signal_metadata)


def test_velocity_keeps_down_penalty_when_price_below_sma20():
    # 종가가 SMA20 아래(95)면 하락 벌점 유지(정상).
    df = pd.DataFrame({"SMA_20": _SMA20_TURN_DOWN, "Close": [95] * len(_SMA20_TURN_DOWN)})

    result = analyze_velocity(df)

    assert result.score < 0
    assert any(m.bias == "bearish" for m in result.signal_metadata)
