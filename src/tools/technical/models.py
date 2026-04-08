from datetime import datetime
from pydantic import BaseModel


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


class StrategyResult(BaseModel):
    """Single strategy execution result."""

    name: str
    status: str
    confidence: float
    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]


class TechnicalResult(BaseModel):
    """Complete technical analysis result."""

    ticker: str
    timestamp: datetime

    # Raw indicators
    indicators: IndicatorSnapshot

    # Strategy results
    strategies: list[StrategyResult]

    # Summary
    overall_assessment: str
    confidence_score: float
    key_insights: list[str]
    warnings: list[str]
