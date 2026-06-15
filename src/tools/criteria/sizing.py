"""포지션 사이징 (Plan 8).

손절 3후보:
  ① entry * 0.92  (-8%)
  ② atr_stop      (2×ATR)
  ③ invalidation_low  (zone lower)

선택 규칙:
  1. 후보를 타이트한 순(entry와 가까운 순) 정렬.
  2. 손절폭 < 3% → 스킵 (최소 손절 가드).
  3. 손절폭 > 8% → 상한 가드: 제거.
  4. 유효 후보 중 가장 타이트 채택.
  5. 모두 제거됐으면 error="risk_too_wide".

per_share_risk = entry - stop; <= 0 → error="invalid_stop".
capital 있으면 shares = floor(capital * risk_pct / per_share_risk).
capital 없으면 capital_mode="ratio", shares=None.
"""

from __future__ import annotations

import math

from src.tools.playbook.models import PositionPlan


_MIN_STOP_PCT = 0.03  # 최소 3% 손절폭
_MAX_STOP_PCT = 0.08  # 최대 8% 손절폭 상한


def plan_position(
    *,
    entry: float,
    atr_stop: float | None,
    invalidation_low: float | None,
    capital: float | None,
    risk_pct: float,
) -> PositionPlan:
    """포지션 사이징. 순수 함수 — I/O 없음."""
    # ── 손절 후보 구성 ────────────────────────────────────────────────────────
    candidates: list[tuple[float, str]] = []

    # ①: -8%
    c1 = entry * (1.0 - _MAX_STOP_PCT)
    candidates.append((c1, "-8%"))

    # ②: 2×ATR
    if atr_stop is not None and atr_stop < entry:
        candidates.append((atr_stop, "2xATR"))

    # ③: zone invalidation
    if invalidation_low is not None and invalidation_low < entry:
        candidates.append((invalidation_low, "zone"))

    # 타이트한 순 정렬 (entry에서 가까운 = stop 값이 큰 순)
    candidates.sort(key=lambda x: x[0], reverse=True)

    # ── 후보 필터링 ───────────────────────────────────────────────────────────
    valid_candidates: list[tuple[float, str]] = []
    for stop_price, basis in candidates:
        pct = (entry - stop_price) / entry
        if pct < _MIN_STOP_PCT:
            continue  # 너무 타이트 → 스킵
        if pct > _MAX_STOP_PCT:
            continue  # 너무 넓음 → 상한 가드
        valid_candidates.append((stop_price, basis))

    if not valid_candidates:
        # 모두 제거 → risk_too_wide
        fallback_stop = entry * (1.0 - _MAX_STOP_PCT)
        return PositionPlan(
            entry=entry,
            stop=fallback_stop,
            stop_basis="-8%",
            per_share_risk=entry - fallback_stop,
            shares=None,
            position_value=None,
            weight_pct=None,
            r_targets={},
            capital_mode="ratio" if capital is None else "absolute",
            error="risk_too_wide",
        )

    # 가장 타이트한 유효 후보 채택
    stop, basis = valid_candidates[0]
    per_share_risk = entry - stop

    if per_share_risk <= 0:
        return PositionPlan(
            entry=entry,
            stop=stop,
            stop_basis=basis,
            per_share_risk=per_share_risk,
            shares=None,
            position_value=None,
            weight_pct=None,
            r_targets={},
            capital_mode="ratio" if capital is None else "absolute",
            error="invalid_stop",
        )

    # ── R 목표 ────────────────────────────────────────────────────────────────
    r_unit = entry - stop
    r_targets = {
        "+2R": round(entry + 2 * r_unit, 4),
        "+3R": round(entry + 3 * r_unit, 4),
    }

    # ── 수량 계산 ─────────────────────────────────────────────────────────────
    if capital is None:
        return PositionPlan(
            entry=entry,
            stop=stop,
            stop_basis=basis,
            per_share_risk=round(per_share_risk, 4),
            shares=None,
            position_value=None,
            weight_pct=None,
            r_targets=r_targets,
            capital_mode="ratio",
            error=None,
        )

    shares = math.floor(capital * risk_pct / per_share_risk)
    position_value = round(shares * entry, 2)
    weight_pct = round(position_value / capital * 100, 2)

    return PositionPlan(
        entry=entry,
        stop=round(stop, 4),
        stop_basis=basis,
        per_share_risk=round(per_share_risk, 4),
        shares=shares,
        position_value=position_value,
        weight_pct=weight_pct,
        r_targets=r_targets,
        capital_mode="absolute",
        error=None,
    )
