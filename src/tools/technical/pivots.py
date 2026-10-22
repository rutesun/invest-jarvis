"""확정 스윙 저점·고점.

저점(고점)은 앞 3봉보다 낮고(높고) 뒤 3봉 이하(이상)일 때 성립한다. 뒤 3봉을 봐야
확정되므로 i번 봉의 피벗은 i+3번 봉 종가부터 알려진 것으로 처리한다(미래 봉 미사용).
IndicatorCalculator의 Swing_High/Low는 중심 창이라 과거 시점 판정에 쓸 수 없다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np


PIVOT_SPAN = 3


@dataclass(frozen=True)
class ConfirmedPivot:
    pivot_type: Literal["HIGH", "LOW"]
    pivot_index: int
    confirmed_index: int
    price: float
    previous_pivot_index: int | None
    previous_pivot_price: float | None
    relation: Literal["HIGHER_HIGH", "HIGHER_LOW", "LOWER_HIGH", "LOWER_LOW"] | None


def confirmed_pivot_events(
    high: np.ndarray, low: np.ndarray, *, final_mask: Sequence[bool] | np.ndarray | None = None
) -> tuple[ConfirmedPivot, ...]:
    """우측 3봉으로 확인하며, FINAL 부분집합 사용 시 원래 봉 index를 돌려준다."""
    if final_mask is not None:
        indices = np.flatnonzero(final_mask)
        return tuple(
            replace(
                event,
                pivot_index=int(indices[event.pivot_index]),
                confirmed_index=int(indices[event.confirmed_index]),
                previous_pivot_index=(
                    int(indices[event.previous_pivot_index])
                    if event.previous_pivot_index is not None
                    else None
                ),
            )
            for event in confirmed_pivot_events(high[indices], low[indices])
        )
    span = PIVOT_SPAN
    events = []
    previous: dict[str, ConfirmedPivot] = {}
    for i in range(span, len(low) - span):
        candidates = []
        if low[i] < low[i - span : i].min() and low[i] <= low[i + 1 : i + span + 1].min():
            candidates.append(("LOW", float(low[i])))
        if high[i] > high[i - span : i].max() and high[i] >= high[i + 1 : i + span + 1].max():
            candidates.append(("HIGH", float(high[i])))
        for pivot_type, price in candidates:
            prior = previous.get(pivot_type)
            relation = None
            if prior is not None and price != prior.price:
                relation = f"{'HIGHER' if price > prior.price else 'LOWER'}_{pivot_type}"
            event = ConfirmedPivot(
                pivot_type=pivot_type,
                pivot_index=i,
                confirmed_index=i + span,
                price=price,
                previous_pivot_index=prior.pivot_index if prior is not None else None,
                previous_pivot_price=prior.price if prior is not None else None,
                relation=relation,
            )
            events.append(event)
            previous[pivot_type] = event
    return tuple(events)


def confirmed_pivots(high: np.ndarray, low: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """봉마다 (마지막 두 확정 저점이 상승, 저점·고점이 동시에 하락) 여부."""
    n = len(low)
    events = confirmed_pivot_events(high, low)
    pivot_lows = [
        (event.confirmed_index, event.price) for event in events if event.pivot_type == "LOW"
    ]
    pivot_highs = [
        (event.confirmed_index, event.price) for event in events if event.pivot_type == "HIGH"
    ]

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
