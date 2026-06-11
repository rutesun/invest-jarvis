"""Stage2 7조건 일원화 테스트.

7조건:
  1. ma_stack: close > sma_150 > sma_200
  2. ma_50_stack: sma_50 > sma_150 > sma_200  [신규]
  3. sma_150_rising: sma_150 > sma_150 21일 전  [신규]
  4. sma_200_rising: sma_200 > sma_200 21일 전
  5. above_50: close > sma_50
  6. above_52w_low_30pct: close >= low_52w * 1.30
  7. within_52w_high_25pct: close >= high_52w * 0.75
"""

import numpy as np
import pandas as pd

from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.indicators import IndicatorCalculator


def _make_df(n: int = 260, start: float = 100.0, end: float = 200.0) -> pd.DataFrame:
    """단조 상승 OHLCV + 지표 계산 완료 df."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    close = np.linspace(start, end, n)
    raw = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": [1_000_000] * n,
        },
        index=dates,
    )
    return IndicatorCalculator().calculate(raw)


def test_stage2_all_7_conditions_met():
    """단조 상승 → 7조건 모두 충족 → is_stage2 == 1.0, score == 40."""
    df = _make_df(260, 100.0, 200.0)
    result = analyze_minervini(df)
    assert result.metrics["is_stage2"] == 1.0, f"metrics={result.metrics}"
    assert result.score == 40
    assert any("Stage 2" in s for s in result.signals)


def test_stage2_below_sma50_fails():
    """종가가 SMA50 아래 → 7조건 미충족 → is_stage2 == 0.0."""
    # 하락 추세 → SMA50 위에 종가 없음
    df = _make_df(260, 200.0, 100.0)
    result = analyze_minervini(df)
    assert result.metrics["is_stage2"] == 0.0, f"metrics={result.metrics}"


def test_is_stage2_in_metrics():
    """metrics 딕셔너리에 is_stage2 키가 항상 존재해야 한다."""
    df = _make_df(260)
    result = analyze_minervini(df)
    assert "is_stage2" in result.metrics


def test_conditions_met_count_7_when_stage2():
    """Stage2 충족 시 conditions_met == 7.0."""
    df = _make_df(260, 100.0, 200.0)
    result = analyze_minervini(df)
    if result.metrics["is_stage2"] == 1.0:
        assert result.metrics["conditions_met"] == 7.0
