"""Compatibility entrypoints for the common confirmed-pivot numerical owner."""

from collections.abc import Sequence

import numpy as np

from src.tools.technical.chart_analysis import pivots as _owner
from src.tools.technical.chart_analysis.pivots import PIVOT_SPAN, ConfirmedPivot


def confirmed_pivot_events(
    high: np.ndarray, low: np.ndarray, *, final_mask: Sequence[bool] | np.ndarray | None = None
) -> tuple[ConfirmedPivot, ...]:
    """우측 3봉으로 확인하며, FINAL 부분집합 사용 시 원래 봉 index를 돌려준다."""
    return _owner.confirmed_pivot_events(high, low, final_mask=final_mask)


def confirmed_pivots(high: np.ndarray, low: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """봉마다 (마지막 두 확정 저점이 상승, 저점·고점이 동시에 하락) 여부."""
    return _owner.confirmed_pivots(high, low)


__all__ = ["ConfirmedPivot", "PIVOT_SPAN", "confirmed_pivot_events", "confirmed_pivots"]
