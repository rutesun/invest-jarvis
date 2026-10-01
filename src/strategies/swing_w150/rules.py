"""SWING_W150 v3 규칙.

진입 경로는 두 가지다.
- S(돌파): 상승하는 150일선 위에서 직전 50봉 고가를 거래량과 함께 처음 넘는 날.
- D(바닥): 200일선 아래지만 20·50일선을 되찾고 저점이 높아지는 바닥에서 20봉 고가 첫 돌파
  또는 50일선 재탈환.
판정은 t 종가, 진입은 t+1 시가, 청산은 종가(손절만 장중 손절가).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.tools.technical.pivots import confirmed_pivots


WARMUP_BARS = 250
S_VOLUME_MULT = 1.4
S_ATR_STOP_MULT = 3.0
D_ATR_STOP_BUFFER = 0.5
D_MAX_LOSS = 0.15
BREAKDOWN_VOLUME_MULT = 1.5
WEAK_CLOSE_LOCATION = 0.25
OVERHEAT_ARM_EXTENSION = 0.40
S_BREAKOUT_LOOKBACK = 50
D_BREAKOUT_LOOKBACK = 20


@dataclass(frozen=True)
class SwingFeatures:
    """IndicatorCalculator 결과를 규칙이 쓰는 배열로 모은 것. 모든 배열은 봉 수와 길이가 같다."""

    dates: list
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    sma20: np.ndarray
    sma50: np.ndarray
    sma150: np.ndarray
    slope150: np.ndarray
    atr: np.ndarray
    low20: np.ndarray
    s_trigger: np.ndarray
    d_trigger: np.ndarray
    deep: np.ndarray


def _prev(a: np.ndarray) -> np.ndarray:
    return np.r_[np.nan, a[:-1]]


def close_location(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """봉 안에서 종가 위치(0=저가, 1=고가). 고저가 같으면 0.5."""
    rng = high - low
    return np.where(rng > 0, (close - low) / np.where(rng > 0, rng, 1), 0.5)


def s_trigger(ind: pd.DataFrame) -> np.ndarray:
    c = ind["Close"].values.astype(float)
    v = ind["Volume"].values.astype(float)
    sma150 = ind["SMA_150"].values
    slope150 = ind["SMA_150_Slope_21"].values
    hi50p = ind["High_50_Prev"].values
    vol20 = ind["Vol_SMA_20"].values
    # 전날 기준선이 없으면 '처음 돌파'를 판정할 수 없으므로 신호로 보지 않는다.
    known = ~np.isnan(sma150) & ~np.isnan(slope150) & ~np.isnan(vol20) & ~np.isnan(hi50p)
    known &= ~np.isnan(_prev(hi50p))
    breakout = (c > hi50p) & ~(_prev(c) > _prev(hi50p))
    return known & (c > sma150) & (slope150 > 0) & breakout & (v > S_VOLUME_MULT * vol20)


def structure_breakdown(ind: pd.DataFrame, st: np.ndarray, lhll: np.ndarray) -> np.ndarray:
    """거래량 동반 20봉 저가 이탈, 약한 종가의 50일선 이탈, 200일선 아래 하락 구조."""
    c, h, low, v = (ind[k].values.astype(float) for k in ("Close", "High", "Low", "Volume"))
    sma50, sma200 = ind["SMA_50"].values, ind["SMA_200"].values
    vr20 = v / ind["Vol_SMA_20_Prev"].values
    cl = close_location(h, low, c)
    return (
        ((c < ind["Low_20_Prev"].values) & (vr20 >= BREAKDOWN_VOLUME_MULT))
        | ((c < sma50) & (cl <= WEAK_CLOSE_LOCATION) & (vr20 >= BREAKDOWN_VOLUME_MULT) & (st == -1))
        | ((c < sma200) & (c < sma50) & (st == -1) & lhll)
    )


def deep_recovery(
    ind: pd.DataFrame, st: np.ndarray, hb: np.ndarray, higher_low: np.ndarray
) -> np.ndarray:
    c = ind["Close"].values.astype(float)
    return (
        ~hb
        & (c < ind["SMA_200"].values)
        & (c > ind["SMA_20"].values)
        & (c > ind["SMA_50"].values)
        & (ind["SMA_20_Slope_5"].values > 0)
        & higher_low
        & (st == 1)
    )


def d_trigger(ind: pd.DataFrame, deep: np.ndarray) -> np.ndarray:
    c = ind["Close"].values.astype(float)
    hi20p, sma50 = ind["High_20_Prev"].values, ind["SMA_50"].values
    fresh20 = (c > hi20p) & ~(_prev(c) > _prev(hi20p))
    reclaim50 = (_prev(c) <= _prev(sma50)) & (c > sma50)
    return deep & (fresh20 | reclaim50)


def build_features(ind: pd.DataFrame) -> SwingFeatures:
    """ind: IndicatorCalculator.calculate 결과."""
    h, low = ind["High"].values.astype(float), ind["Low"].values.astype(float)
    # pandas_ta 슈퍼트렌드는 워밍업 구간이 NaN이다. 기준 백테스트는 이를 상승(1)으로 둔다.
    st = np.nan_to_num(ind["SuperTrend_Dir"].values.astype(float), nan=1.0)
    higher_low, lhll = confirmed_pivots(h, low)
    hb = structure_breakdown(ind, st, lhll)
    deep = deep_recovery(ind, st, hb, higher_low)
    return SwingFeatures(
        dates=[x.date() for x in ind.index],
        open=ind["Open"].values.astype(float),
        high=h,
        low=low,
        close=ind["Close"].values.astype(float),
        sma20=ind["SMA_20"].values,
        sma50=ind["SMA_50"].values,
        sma150=ind["SMA_150"].values,
        slope150=ind["SMA_150_Slope_21"].values,
        atr=ind["ATR"].values,
        low20=ind["Low_20"].values,
        s_trigger=s_trigger(ind),
        d_trigger=d_trigger(ind, deep),
        deep=deep,
    )


def trigger_kind(f: SwingFeatures, t: int) -> str | None:
    """S가 D보다 우선."""
    if f.s_trigger[t]:
        return "S"
    if f.d_trigger[t]:
        return "D"
    return None


def initial_stop(kind: str, entry: float, f: SwingFeatures, t: int) -> float:
    # builtin min/max를 쓴다: 기준 동작은 NaN이 섞이면 첫 인자를 돌려주는 파이썬 규칙에 기대고,
    # 그 결과 NaN 손절은 이후 'stop < entry' 검사에서 걸러진다.
    atr = float(f.atr[t])
    if kind == "S":
        return min(float(f.sma150[t]), entry - S_ATR_STOP_MULT * atr)
    return max(float(f.low20[t]) - D_ATR_STOP_BUFFER * atr, entry * (1 - D_MAX_LOSS))


def graduates(f: SwingFeatures, k: int) -> bool:
    """D 진입은 상승하는 150일선 위로 올라선 뒤부터 150일선 청산 규칙을 적용받는다."""
    return bool(f.close[k] > f.sma150[k] and f.slope150[k] > 0)


def below_exit_line(f: SwingFeatures, k: int) -> bool:
    return bool(f.close[k] < f.sma150[k])


def exit_150(f: SwingFeatures, k: int, below: bool, prev_below: bool, risk: float) -> bool:
    """150일선 아래 2일 연속, 또는 150일선보다 1R 이상 아래에서 마감."""
    return (below and prev_below) or bool(f.close[k] < f.sma150[k] - risk)


def overheat_armed(f: SwingFeatures, k: int) -> bool:
    return bool(f.close[k] / f.sma50[k] - 1 >= OVERHEAT_ARM_EXTENSION)


def overheat_sell(f: SwingFeatures, k: int) -> bool:
    """과열 무장 뒤 20일선을 처음 종가로 이탈하면 전량 매도."""
    return bool(f.close[k] < f.sma20[k] and f.close[k - 1] >= f.sma20[k - 1])


def overheat_rebuy(f: SwingFeatures, k: int) -> bool:
    """과열 매도 뒤 20일선 위 + 전일 고가 돌파 마감이면 다시 산다."""
    return bool(f.close[k] > f.sma20[k] and f.close[k] > f.high[k - 1])
