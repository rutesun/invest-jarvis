"""brief 도메인 모델 — 종목별 판정 결과 집계 단위."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.tools.disclosure import DisclosureItem
from src.tools.flow import InvestorFlow
from src.tools.news import NewsArticle
from src.tools.playbook.holdings import HoldingEntry
from src.tools.playbook.models import PlaybookVerdict


# 버킷 순서 = 절대 우선순위 (낮을수록 상단). 스펙 §5.2
BUCKET_LIQUIDATE = 1  # 청산 — "놓치면 손실"
BUCKET_BUY_ELIGIBLE = 2  # 매수 적격 — "놓치면 기회"
BUCKET_REDUCE = 3  # 비중축소
BUCKET_IMMINENT = 4  # 진입 임박
BUCKET_HOLD_WARN = 5  # 보유(약신호 있음)
BUCKET_REJECTED = 6  # 거부(워치)
BUCKET_HOLD_OK = 7  # 보유(이상 없음) / 데이터 실패

BUCKET_LABELS: dict[int, str] = {
    BUCKET_LIQUIDATE: "청산",
    BUCKET_BUY_ELIGIBLE: "매수 적격",
    BUCKET_REDUCE: "비중축소",
    BUCKET_IMMINENT: "진입 임박",
    BUCKET_HOLD_WARN: "보유(약신호)",
    BUCKET_REJECTED: "거부",
    BUCKET_HOLD_OK: "보유",
}


@dataclass
class BriefItem:
    """종목 하나의 브리핑 항목 — 규칙 판정 결과 + 근거 데이터 집계."""

    ticker: str
    kind: str  # "holding" | "watch"
    action: str  # "liquidate"|"reduce"|"hold"|"eligible"|"imminent"|"rejected"|"error"
    bucket: int
    bonus: int = 0
    markers: list[str] = field(default_factory=list)  # "스탑 근접", "급변: ..." 등
    note: str | None = None  # watchlist note
    holding: HoldingEntry | None = None
    verdict: PlaybookVerdict | None = None
    news: list[NewsArticle] = field(default_factory=list)
    disclosures: list[DisclosureItem] = field(default_factory=list)
    flow: InvestorFlow | None = None
    price: float | None = None
    change_pct: float | None = None
    remaining_condition: str | None = None  # 임박 시 미충족 게이트 1개
    narrative: Any | None = None  # TickerNarrative (Task 4) — 순환 import 방지로 Any
    error: str | None = None
