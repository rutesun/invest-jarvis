"""VCP 피벗 돌파 테스트.

_detect_vcp(수축 판정)를 재사용하고, 마지막 봉이 직전 N일 고점(피벗) 상향 돌파 +
거래량 >= Vol_SMA_50 × 1.5 이면 breakout=True.
"""

import numpy as np
import pandas as pd

from src.tools.criteria.models import VcpResult
from src.tools.criteria.vcp import detect_vcp_breakout


def _base_df(n: int = 60) -> pd.DataFrame:
    """최소 지표 컬럼이 포함된 OHLCV DataFrame.

    _detect_vcp는 최근 8개 ATR을 체크한다 (atr_series.iloc[-8:]).
    앞 4개 = 5.0, 뒤 4개 = 2.0 → contraction_ratio = 0.6 > 0.20 → Stage1 통과.
    """
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    close = np.linspace(100, 110, n)
    vol = np.full(n, 1_000_000.0)
    df = pd.DataFrame(
        {
            "Open": close - 0.3,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": vol,
        },
        index=idx,
    )
    # Vol_SMA_50 컬럼 직접 추가 (약 1_000_000)
    df["Vol_SMA_50"] = 1_000_000.0
    # ATR 수축: 마지막 8개 = [5,5,5,5, 2,2,2,2] → contraction_ratio = (5-2)/5 = 0.6 > 0.20
    atr = [3.0] * (n - 8) + [5.0, 5.0, 5.0, 5.0, 2.0, 2.0, 2.0, 2.0]
    df["ATR"] = atr
    return df


def _make_breakout_df() -> pd.DataFrame:
    """수축 후 마지막 봉이 직전 20일 고점을 돌파하고 거래량 급증."""
    df = _base_df(60)
    # 직전 20일 고점 = close[-21:-1].max()의 High
    # 마지막 봉 Close > 피벗, Volume >= Vol_SMA_50 * 1.5
    # 현재 High 열은 close+1, 직전 20일 중 최대 close ≈ 109(idx=-2 근방)
    # 마지막 봉을 직전 구간 고점보다 훨씬 높게 설정
    pivot_high = float(df["High"].iloc[-21:-1].max())
    df.loc[df.index[-1], "Close"] = pivot_high + 2.0
    df.loc[df.index[-1], "High"] = pivot_high + 2.0
    df.loc[df.index[-1], "Volume"] = 2_000_000.0  # >= 1_000_000 * 1.5
    return df


def _make_contraction_only_df() -> pd.DataFrame:
    """수축만 있고 돌파 없음 (마지막 봉이 피벗 아래)."""
    df = _base_df(60)
    # 마지막 봉 Close < 피벗 (기본값 유지 = 110, 피벗은 거의 같거나 높음)
    pivot_high = float(df["High"].iloc[-21:-1].max())
    df.loc[df.index[-1], "Close"] = pivot_high - 1.0  # 피벗 아래
    df.loc[df.index[-1], "High"] = pivot_high - 0.5
    return df


def test_result_is_vcp_result():
    df = _base_df(60)
    r = detect_vcp_breakout(df)
    assert isinstance(r, VcpResult)


def test_breakout_detected():
    """수축 + 피벗 돌파 + 거래량 급증 → breakout=True, in_vcp=True."""
    df = _make_breakout_df()
    r = detect_vcp_breakout(df)
    assert r.in_vcp is True, f"in_vcp should be True, detail={r.detail}"
    assert r.breakout is True, f"breakout should be True, pivot={r.pivot}, detail={r.detail}"
    assert r.pivot is not None


def test_contraction_no_breakout():
    """수축만, 돌파 없음 → in_vcp=True, breakout=False."""
    df = _make_contraction_only_df()
    r = detect_vcp_breakout(df)
    assert r.in_vcp is True, f"in_vcp should be True, detail={r.detail}"
    assert r.breakout is False, f"breakout should be False, detail={r.detail}"


def test_no_contraction_no_vcp():
    """ATR 수축 없음 → in_vcp=False, breakout=False."""
    idx = pd.date_range("2023-01-01", periods=60, freq="B")
    close = np.linspace(100, 110, 60)
    df = pd.DataFrame(
        {
            "Open": close - 0.3,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": [1_000_000.0] * 60,
        },
        index=idx,
    )
    df["Vol_SMA_50"] = 1_000_000.0
    df["ATR"] = 3.0  # 일정 ATR → 수축 없음(contraction_ratio ≤ 0)
    r = detect_vcp_breakout(df)
    assert r.in_vcp is False
    assert r.breakout is False


def test_detail_not_empty():
    df = _base_df(60)
    r = detect_vcp_breakout(df)
    assert r.detail != ""
