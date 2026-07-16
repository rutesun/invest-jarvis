"""brief 랭킹/판정 규칙 — 순수 함수, I/O 없음.

버킷 순서가 절대 우선이고, 가산점(스탑 근접·급변)은 동버킷 내 정렬에만 쓴다.
가산점이 버킷을 역전하면 "축소+스탑근접 > 청산" 같은 왜곡이 생기기 때문 (스펙 §5.2).
"""

from __future__ import annotations

from src.tools.brief.models import (
    BUCKET_BUY_ELIGIBLE,
    BUCKET_HOLD_OK,
    BUCKET_HOLD_WARN,
    BUCKET_IMMINENT,
    BUCKET_LIQUIDATE,
    BUCKET_REDUCE,
    BUCKET_REJECTED,
    BriefItem,
)
from src.tools.playbook.models import GateResult


BONUS_STOP_PROXIMITY = 30
BONUS_SURGE = 20
STOP_PROXIMITY_RATIO = 1.03  # 현재가 <= 스탑 × 1.03 → 근접(이탈 포함)
SURGE_PCT = 5.0  # 당일 등락 ±5% 이상


def classify_watch(gate: GateResult) -> tuple[str, str | None]:
    """워치 종목 판정. 임박 = 필수 게이트 4개 중 정확히 3개 met=True.

    Stage2 개수만 보면 시장 하락·RS 약세를 무시하므로 checklist 기반으로 판정 (스펙 D9).
    """
    if gate.passed:
        return "eligible", None
    required = [c for c in gate.checklist if c.required]
    met_count = sum(1 for c in required if c.met is True)
    if len(required) == 4 and met_count == 3:
        failed = next(c for c in required if c.met is not True)
        return "imminent", f"{failed.name}: {failed.reason}"
    return "rejected", None


def bucket_for(kind: str, action: str, has_warn_signals: bool = False) -> int:
    """(kind, action) → 버킷 번호."""
    if action == "liquidate":
        return BUCKET_LIQUIDATE
    if action == "eligible":
        return BUCKET_BUY_ELIGIBLE
    if action == "reduce":
        return BUCKET_REDUCE
    if action == "imminent":
        return BUCKET_IMMINENT
    if action == "rejected":
        return BUCKET_REJECTED
    if action == "hold" and has_warn_signals:
        return BUCKET_HOLD_WARN
    return BUCKET_HOLD_OK  # hold(무신호) / error


def is_stop_proximate(price: float | None, stop_price: float | None) -> bool:
    """현재가가 스탑 대비 3% 이내(이탈 포함)면 True."""
    if price is None or stop_price is None or stop_price <= 0:
        return False
    return price <= stop_price * STOP_PROXIMITY_RATIO


def surge_reason(kind: str, change_pct: float | None) -> str | None:
    """당일 ±5% 이상 급변 시 방향별 사유. 아니면 None."""
    if change_pct is None or abs(change_pct) < SURGE_PCT:
        return None
    if kind == "holding":
        return "급변: 보유 급등" if change_pct > 0 else "급변: 보유 급락"
    return "급변: 워치 상승 돌파" if change_pct > 0 else "급변: 워치 급락"


def rank(items: list[BriefItem]) -> list[BriefItem]:
    """버킷 오름차순 → 가산점 내림차순. 안정 정렬."""
    return sorted(items, key=lambda i: (i.bucket, -i.bonus))
