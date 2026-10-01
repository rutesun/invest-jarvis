"""확정 스윙 저점·고점.

저점(고점)은 앞 3봉보다 낮고(높고) 뒤 3봉 이하(이상)일 때 성립한다. 뒤 3봉을 봐야
확정되므로 i번 봉의 피벗은 i+3번 봉 종가부터 알려진 것으로 처리한다(미래 봉 미사용).
IndicatorCalculator의 Swing_High/Low는 중심 창이라 과거 시점 판정에 쓸 수 없다.
"""

from __future__ import annotations

import numpy as np


PIVOT_SPAN = 3


def confirmed_pivots(high: np.ndarray, low: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """봉마다 (마지막 두 확정 저점이 상승, 저점·고점이 동시에 하락) 여부."""
    n = len(low)
    span = PIVOT_SPAN
    pivot_lows, pivot_highs = [], []
    for i in range(span, n - span):
        if low[i] < low[i - span : i].min() and low[i] <= low[i + 1 : i + span + 1].min():
            pivot_lows.append((i + span, low[i]))
        if high[i] > high[i - span : i].max() and high[i] >= high[i + 1 : i + span + 1].max():
            pivot_highs.append((i + span, high[i]))

    higher_low = np.zeros(n, bool)
    lower_low_lower_high = np.zeros(n, bool)
    lows, highs, j, k = [], [], 0, 0
    for t in range(n):
        while j < len(pivot_lows) and pivot_lows[j][0] <= t:
            lows.append(pivot_lows[j][1])
            j += 1
        while k < len(pivot_highs) and pivot_highs[k][0] <= t:
            highs.append(pivot_highs[k][1])
            k += 1
        if len(lows) >= 2:
            higher_low[t] = lows[-1] > lows[-2]
            if len(highs) >= 2:
                lower_low_lower_high[t] = lows[-1] < lows[-2] and highs[-1] < highs[-2]
    return higher_low, lower_low_lower_high
