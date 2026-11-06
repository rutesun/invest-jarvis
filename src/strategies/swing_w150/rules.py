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
    from src.tools.technical.chart_analysis import _legacy_structure

    return _legacy_structure._prev(a)


def close_location(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """봉 안에서 종가 위치(0=저가, 1=고가). 고저가 같으면 0.5."""
    from src.tools.technical.chart_analysis import _legacy_structure

    return _legacy_structure.close_location_values(high, low, close)


def s_trigger(ind: pd.DataFrame) -> np.ndarray:
    from src.tools.technical.chart_analysis import _legacy_structure

    close = ind["Close"].values.astype(float)
    volume = ind["Volume"].values.astype(float)
    sma150 = ind["SMA_150"].values
    slope150 = ind["SMA_150_Slope_21"].values
    prior_high = ind["High_50_Prev"].values
    volume_average = ind["Vol_SMA_20"].values
    return _legacy_structure.swing_s01_array_values(
        close,
        prior_high,
        sma150,
        slope150,
        volume,
        volume_average,
        volume_multiple=S_VOLUME_MULT,
    )["trigger"]


def structure_breakdown(
    ind: pd.DataFrame,
    st: np.ndarray,
    lhll: np.ndarray,
    *,
    volume_multiple: float = BREAKDOWN_VOLUME_MULT,
    weak_close_location: float = WEAK_CLOSE_LOCATION,
) -> np.ndarray:
    """거래량 동반 20봉 저가 이탈, 약한 종가의 50일선 이탈, 200일선 아래 하락 구조."""
    from src.tools.technical.chart_analysis import _legacy_structure

    return _legacy_structure.swing_structure_values(
        ind,
        st,
        lhll,
        volume_multiple=volume_multiple,
        weak_close_location=weak_close_location,
    )["structure_breakdown"]


def deep_recovery(
    ind: pd.DataFrame, st: np.ndarray, hb: np.ndarray, higher_low: np.ndarray
) -> np.ndarray:
    from src.tools.technical.chart_analysis import _legacy_structure

    return _legacy_structure.swing_deep_recovery_values(ind, st, hb, higher_low)


def d_trigger(ind: pd.DataFrame, deep: np.ndarray) -> np.ndarray:
    from src.tools.technical.chart_analysis import _legacy_structure

    return _legacy_structure.swing_d_trigger_array_values(
        ind["Close"].values.astype(float),
        ind["High_20_Prev"].values,
        ind["SMA_50"].values,
        deep,
    )["d_trigger"]


def build_features(ind: pd.DataFrame, *, common_analysis=None) -> SwingFeatures:
    """ind: IndicatorCalculator.calculate 결과."""
    h, low = ind["High"].values.astype(float), ind["Low"].values.astype(float)
    # pandas_ta 슈퍼트렌드는 워밍업 구간이 NaN이다. 기준 백테스트는 이를 상승(1)으로 둔다.
    st = np.nan_to_num(ind["SuperTrend_Dir"].values.astype(float), nan=1.0)
    values = None
    if common_analysis is not None:
        from src.strategies.swing_w150.common import (
            requested_items,
            swing_rules,
            validate_frame_analysis,
        )
        from src.strategies.swing_w150.parameters import SwingW150Parameters

        validate_frame_analysis(
            common_analysis, ind, swing_rules(SwingW150Parameters(), replay=True)
        )
        common_items = requested_items(
            common_analysis, swing_rules(SwingW150Parameters(), replay=True)
        )
        values = dict(
            next(
                item.evidence
                for item in common_items
                if item.rule_id == "chart.deep_recovery.swing"
            )
        )
        values["s_trigger"] = next(
            item.evidence["trigger"]
            for item in common_items
            if item.rule_id == "chart.close_breakout.strict"
        )
        deep = np.asarray(values["deep_recovery"], dtype=bool)
    else:
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
        s_trigger=np.asarray(values["s_trigger"], dtype=bool)
        if values is not None
        else s_trigger(ind),
        d_trigger=np.asarray(values["d_trigger"], dtype=bool)
        if values is not None
        else d_trigger(ind, deep),
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
