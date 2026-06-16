from __future__ import annotations

from pydantic import BaseModel, Field


class MacdCross(BaseModel):
    """MACD 라인과 시그널선의 최근 교차 사건."""

    cross_type: str  # "golden" | "dead"
    date: str  # ISO date (YYYY-MM-DD)
    days_ago: int
    macd: float
    signal: float


class RsiDivergence(BaseModel):
    """가격과 RSI 간 다이버전스 사건."""

    divergence_type: str  # "bullish" | "bearish"
    date: str
    days_ago: int
    detail: str  # "가격 고점 상승, RSI 고점 하락 (72→68)"


class PriceEvent(BaseModel):
    """가격/구조 사건 (신고가 돌파/실패, 스윙로우 이탈/유지)."""

    code: str  # "NEW_HIGH_BREAKOUT" | "NEW_HIGH_FAIL" | "SWING_LOW_BREAK" | "SWING_LOW_HELD"
    side: str  # "bull" | "bear" | "neutral"
    headline: str
    detail: str
    date: str | None = None
    days_ago: int | None = None


class RsEvent(BaseModel):
    """상대강도(Mansfield RS) 음↔양 전환 사건."""

    cross_type: str  # "양전환" | "음전환"
    date: str
    days_ago: int
    detail: str


class MomentumEvents(BaseModel):
    """deep_dive가 result dict에 싣는 신규 사건 묶음."""

    macd_cross: MacdCross | None = None
    rsi_divergence: RsiDivergence | None = None
    ud_volume_ratio: float | None = None
    volume_trend: str | None = None  # "증가" | "감소" | "횡보"
    price_events: list[PriceEvent] = Field(default_factory=list)
    rs_event: RsEvent | None = None
