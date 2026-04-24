from datetime import datetime

import pandas as pd
from pydantic import BaseModel, Field


class ComponentResult(BaseModel):
    """Result from a technical analysis component."""

    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]
    score: int


class IndicatorSnapshot(BaseModel):
    """Raw indicator values snapshot."""

    # Price
    price: float
    change_pct: float

    # Moving averages
    sma_10: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_120: float | None = None
    sma_150: float | None = None
    sma_200: float | None = None

    # Momentum
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    # Volatility
    atr: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None

    # Trend strength
    adx: float | None = None
    supertrend_direction: int | None = None

    # Disparity
    disparity_20: float | None = None
    disparity_50: float | None = None
    disparity_120: float | None = None

    # Support/Resistance
    pivot: float | None = None
    support_s1: float | None = None
    resistance_r1: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None

    # Cycle RSI
    crsi: float | None = None
    crsi_high_band: float | None = None
    crsi_low_band: float | None = None

    # Volume
    vol_sma_20: float | None = None
    vol_sma_50: float | None = None
    vol_sma_120: float | None = None

    # Swing Points
    swing_high: float | None = None
    swing_low: float | None = None

    # Gap
    is_gap_up: bool | None = None
    is_gap_down: bool | None = None

    # Fast MACD (5/35/5)
    macd_fast: float | None = None
    macd_fast_signal: float | None = None
    macd_fast_histogram: float | None = None


class StrategyResult(BaseModel):
    """Single strategy execution result."""

    name: str
    status: str
    confidence: float
    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]


class ChartPatternResult(BaseModel):
    """차트 패턴 감지 결과"""

    pattern_name: str
    detected: bool
    confidence: float = Field(ge=0.0, le=1.0)

    # 타이밍 정보
    completed_date: str | None = None
    days_ago: int | None = None

    # 가격 정보
    current_price: float
    breakout_level: float | None = None
    support_level: float | None = None

    # 상세 정보
    description: str
    key_levels: dict = Field(default_factory=dict)


class PriceLevel(BaseModel):
    """개별 가격 레벨"""

    price: float
    type: str
    distance_pct: float
    description: str


class PriceLevels(BaseModel):
    """통합 가격 레벨 정보"""

    current_price: float
    support_levels: list[PriceLevel] = Field(default_factory=list)
    resistance_levels: list[PriceLevel] = Field(default_factory=list)
    targets: dict[str, float] = Field(default_factory=dict)


class TechnicalResult(BaseModel):
    """Complete technical analysis result."""

    ticker: str | None
    timestamp: datetime
    snapshot: IndicatorSnapshot
    components: dict[str, dict]
    total_score: int = 0

    # NEW: Pattern detection requires OHLC data
    raw_dataframe: pd.DataFrame | None = None

    # Legacy fields for backward compatibility
    indicators: IndicatorSnapshot | None = None
    strategies: list[StrategyResult] | None = None
    overall_assessment: str | None = None
    confidence_score: float | None = None
    key_insights: list[str] | None = None
    warnings: list[str] | None = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_analysis(cls, df: pd.DataFrame, **kwargs):
        """메모리 최적화: OHLC 컬럼만 저장"""
        slim_df = df[["Open", "High", "Low", "Close"]].copy()
        return cls(raw_dataframe=slim_df, **kwargs)
