"""턴어라운드 스코어러 유닛 테스트 — 각 마커를 결정론적 합성 df로 격리 검증."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.turnaround import (
    DEFAULT_THRESHOLD,
    TurnaroundSignal,
    score_turnaround,
)


def build_df(n: int = 40, **overrides) -> pd.DataFrame:
    """마커가 하나도 발화하지 않는 중립 df를 만든 뒤 override 적용.

    기본값: 종가 100 평탄, 시가=종가(양봉 아님), 저가 99/고가 101,
    SMA_20=SMA_50=101(종가 위 → weak_context True), cRSI 50(과매도 아님),
    cRSI_LowBand 30, Vol_SMA_20=거래량(급증 아님), SuperTrend_Dir -1(미확인).
    """
    close = np.full(n, 100.0)
    data = {
        "Open": close.copy(),
        "High": np.full(n, 101.0),
        "Low": np.full(n, 99.0),
        "Close": close,
        "Volume": np.full(n, 1_000_000.0),
        "SMA_20": np.full(n, 101.0),
        "SMA_50": np.full(n, 101.0),
        "Vol_SMA_20": np.full(n, 1_000_000.0),
        "cRSI": np.full(n, 50.0),
        "cRSI_LowBand": np.full(n, 30.0),
        "SuperTrend_Dir": np.full(n, -1.0),
    }
    for key, value in overrides.items():
        data[key] = np.asarray(value, dtype=float)
    return pd.DataFrame(data)


def test_none_and_empty_return_empty_signal():
    assert score_turnaround(None).score == 0
    assert score_turnaround(pd.DataFrame()).score == 0


def test_missing_required_columns_returns_empty():
    df = pd.DataFrame({"Close": np.full(40, 100.0)})
    signal = score_turnaround(df)
    assert isinstance(signal, TurnaroundSignal)
    assert signal.score == 0
    assert signal.markers == []


def test_neutral_df_fires_no_markers():
    signal = score_turnaround(build_df())
    assert signal.score == 0
    assert signal.markers == []
    assert signal.is_candidate is False


def test_higher_low_marker():
    low = np.full(40, 99.0)
    low[40 - 15 : 40 - 5] = 90.0  # 이전 저점 구간 낮게
    low[40 - 5 :] = 95.0  # 최근 저점 구간 높게 → higher low
    signal = score_turnaround(build_df(Low=low))
    assert "higher_low" in signal.markers


def test_volume_surge_marker():
    open_ = np.full(40, 100.0)
    close = np.full(40, 100.0)
    open_[-1] = 99.0  # 마지막 바 양봉
    volume = np.full(40, 1_000_000.0)
    volume[-1] = 3_000_000.0  # 20일평균 1.5배 초과
    signal = score_turnaround(build_df(Open=open_, Close=close, Volume=volume))
    assert "volume_surge" in signal.markers


def test_ma_reclaim_marker():
    close = np.full(40, 100.0)
    close[-1] = 102.0  # 마지막 바 SMA_20(101) 상향 돌파 (전일 100 <= 101)
    signal = score_turnaround(build_df(Close=close))
    assert "ma_reclaim" in signal.markers


def test_oversold_rebound_marker():
    high = np.full(40, 101.0)
    high[0:20] = 130.0  # 과거 고점 → 현재가 100은 -23% 급락 상태
    crsi = np.full(40, 50.0)
    crsi[-2] = 25.0  # 전일 하단밴드(30) 아래
    crsi[-1] = 32.0  # 당일 상향 돌파 + 과매도(35 미만)
    signal = score_turnaround(build_df(High=high, cRSI=crsi))
    assert "oversold_rebound" in signal.markers


def test_confirmed_reflects_supertrend():
    up = np.full(40, -1.0)
    up[-1] = 1.0
    assert score_turnaround(build_df(SuperTrend_Dir=up)).confirmed is True
    assert score_turnaround(build_df()).confirmed is False


def test_candidate_requires_threshold_and_weak_context():
    # higher_low + volume_surge = score 2, 종가<SMA50 → weak True → 후보
    low = np.full(40, 99.0)
    low[40 - 15 : 40 - 5] = 90.0
    low[40 - 5 :] = 95.0
    open_ = np.full(40, 100.0)
    open_[-1] = 99.0
    volume = np.full(40, 1_000_000.0)
    volume[-1] = 3_000_000.0
    signal = score_turnaround(build_df(Low=low, Open=open_, Volume=volume))
    assert signal.score >= DEFAULT_THRESHOLD
    assert signal.is_candidate is True

    # 같은 마커지만 SMA가 종가 아래 → 약세 맥락 아님 → 후보 아님
    not_weak = score_turnaround(
        build_df(
            Low=low,
            Open=open_,
            Volume=volume,
            SMA_20=np.full(40, 95.0),
            SMA_50=np.full(40, 95.0),
        )
    )
    assert not_weak.score >= DEFAULT_THRESHOLD
    assert not_weak.is_candidate is False


def test_stop_level_is_recent_swing_low():
    low = np.full(40, 99.0)
    low[-3] = 88.0  # 최근 7바 윈도우 내 최저
    signal = score_turnaround(build_df(Low=low))
    assert signal.stop_level == 88.0
    assert signal.stop_pct is not None and signal.stop_pct < 0


def test_summary_line_contains_markers_and_status():
    low = np.full(40, 99.0)
    low[40 - 15 : 40 - 5] = 90.0
    low[40 - 5 :] = 95.0
    signal = score_turnaround(build_df(Low=low))
    line = signal.summary_line()
    assert "턴어라운드" in line
    assert "저점 높이기" in line


def test_integration_with_indicator_calculator():
    """실제 IndicatorCalculator 산출 df와 컬럼 호환성 확인."""
    rng = np.random.default_rng(7)
    n = 260
    close = 100 + np.cumsum(rng.standard_normal(n) * 2)
    df = pd.DataFrame(
        {
            "Open": close - rng.random(n),
            "High": close + rng.random(n) * 2,
            "Low": close - rng.random(n) * 2,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )
    calc = IndicatorCalculator().calculate(df)
    signal = score_turnaround(calc)
    assert isinstance(signal, TurnaroundSignal)
    assert 0 <= signal.score <= 4
