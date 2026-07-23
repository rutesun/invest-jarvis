from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field


class RelativeStrengthResult(BaseModel):
    """맨스필드식 종목 상대강도 (종목 vs 시장). RSI와 무관."""

    mansfield_rs: float  # (RP / SMA(RP,252) - 1) * 100
    outperform_6m: float  # 종목 6M 수익률 - 지수 6M 수익률 (%p)
    rp_slope_4w: float  # 상대가격선 4주(20거래일) 변화
    index_symbol: str

    @computed_field
    @property
    def is_strong(self) -> bool:
        return self.mansfield_rs > 0 and self.rp_slope_4w >= 0


class AccumulationResult(BaseModel):
    """오닐식 매집일/분산일 집계 (CAN SLIM I)."""

    accumulation_days: int
    distribution_days: int
    accumulation_ratio: float  # acc / (acc + dist); 분모 0이면 0.0
    window: int

    @computed_field
    @property
    def is_accumulating(self) -> bool:
        return self.accumulation_ratio > 0.5


class SectorStrengthResult(BaseModel):
    """업종 강도 (게이트 C★ 업종 조건 + CAN SLIM L)."""

    industry: str | None
    rank_pct: float | None  # 미국: 전체 업종 중 백분위(0=최강). 한국: None(코스피 대비로 대체)
    trend: str  # "up" | "down" | "flat" | "unknown"
    is_strong: bool | None  # None = 매핑 실패/데이터 없음 → 게이트는 종목 RS만(graceful)
    source: str  # "FMP" | "KIS" | "none"
    detail: str = ""


class MarketRegimeResult(BaseModel):
    """시장환경 게이트 결과 (지수 추세 기반)."""

    regime: str  # "상승" | "조정" | "하락" | "unknown"
    allow_new_buy: bool
    index_symbol: str
    detail: str = ""


class VcpResult(BaseModel):
    """VCP(Volatility Contraction Pattern) 피벗 돌파 결과."""

    in_vcp: bool
    pivot: float | None = None
    breakout: bool
    detail: str = Field(default="")


class ElementVerdict(BaseModel):
    """CAN SLIM 단일 요소 판정 결과."""

    met: bool | None
    detail: str = ""


class CanslimResult(BaseModel):
    """CAN SLIM 7요소 종합 판정 결과."""

    c: ElementVerdict
    a: ElementVerdict
    n: ElementVerdict
    s: ElementVerdict
    l: ElementVerdict  # noqa: E741
    i: ElementVerdict
    m: ElementVerdict

    @computed_field
    @property
    def score(self) -> int:
        return sum(
            1 for e in (self.c, self.a, self.n, self.s, self.l, self.i, self.m) if e.met is True
        )

    @computed_field
    @property
    def summary(self) -> str:
        order = [
            ("C", self.c),
            ("A", self.a),
            ("N", self.n),
            ("S", self.s),
            ("L", self.l),
            ("I", self.i),
            ("M", self.m),
        ]
        sym = {True: "✅", False: "❌", None: "—"}
        graded = sum(1 for _, e in order if e.met is not None)
        return " ".join(f"{k}{sym[e.met]}" for k, e in order) + f" ({self.score}/{graded})"


# ---------------------------------------------------------------------------
# Plan 8: Gate / Sizing / Exit / Verdict models
# ---------------------------------------------------------------------------


class GateCheck(BaseModel):
    """게이트 체크리스트 단일 항목."""

    name: str
    required: bool
    met: bool | None  # True=통과, False=탈락, None=데이터 없음(보수적 FAIL)
    reason: str


class GateResult(BaseModel):
    """매수 게이트 종합 판정."""

    passed: bool
    checklist: list[GateCheck]
    quality_grade: str | None  # "A" | "B" | "C" | None (게이트 미통과 시)
    veto_reason: str | None  # 가장 결정적 미충족 항목 설명


class PositionPlan(BaseModel):
    """포지션 사이징 계획."""

    entry: float
    stop: float
    stop_basis: str  # "-8%" | "2xATR" | "zone"
    per_share_risk: float
    shares: int | None  # capital 없으면 None (ratio 모드)
    position_value: float | None
    weight_pct: float | None  # 자본 대비 비중(%)
    r_targets: dict[str, float]  # {"+2R": price, "+3R": price}
    capital_mode: str  # "absolute" | "ratio"
    error: str | None  # "invalid_stop" | "risk_too_wide" | None


class ExitSignal(BaseModel):
    """매도 신호 단일 항목."""

    code: str  # "CHARACTER_CHANGE" | "SMA_SHORT" | "DISTRIBUTION" | "RS_WEAKENING" | "SMA_LONG"
    severity: str  # "strong" | "medium" | "weak"
    detail: str


class ExitVerdict(BaseModel):
    """보유 종목 매도 판정."""

    action: Literal["liquidate", "reduce", "hold"]
    signals: list[ExitSignal]
    current_r: float | None  # stop_price 있을 때만
    trailing_stop: float | None  # SMA50 기반
    detail: str


class PlaybookVerdict(BaseModel):
    """플레이북 엔진 최종 판정 결과."""

    ticker: str
    holding: bool
    market_regime: MarketRegimeResult
    relative_strength: RelativeStrengthResult
    sector_strength: SectorStrengthResult | None
    canslim: CanslimResult | None
    gate: GateResult | None  # 미보유 시
    position_plan: PositionPlan | None  # 게이트 통과 시
    exit_verdict: ExitVerdict | None  # 보유 시
    headline: str
