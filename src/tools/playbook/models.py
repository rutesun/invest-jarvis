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
