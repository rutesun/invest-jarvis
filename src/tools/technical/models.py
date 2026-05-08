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

    # Performance
    perf_1m: float | None = None
    perf_3m: float | None = None
    perf_6m: float | None = None
    perf_1y: float | None = None

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


class StructureZone(BaseModel):
    """구조적 수요/공급/무효화 zone"""

    zone_type: str
    lower_bound: float
    upper_bound: float
    mid_price: float
    touch_count: int
    last_touch_date: str | None = None
    touch_score: float
    recency_score: float
    volume_reaction_score: float
    confluence_score: float
    total_score: float
    strength: str
    reasons: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    reason_context: dict[str, object] = Field(default_factory=dict)


class StructureZoneSet(BaseModel):
    """구조 zone 계산 결과 묶음"""

    demand_zones: list[StructureZone] = Field(default_factory=list)
    supply_zones: list[StructureZone] = Field(default_factory=list)
    balance_zones: list[StructureZone] = Field(default_factory=list)
    invalidation_candidates: list[StructureZone] = Field(default_factory=list)
    invalidation_zone: StructureZone | None = None
    all_candidates: list[StructureZone] = Field(default_factory=list)
    selection_trace: list[dict[str, object]] = Field(default_factory=list)
    touch_episodes: list[dict[str, object]] = Field(default_factory=list)
    no_clear_structure: bool = False
    no_clear_structure_reason_codes: list[str] = Field(default_factory=list)


class StructureZoneConfig(BaseModel):
    """구조 zone 계산 파라미터"""

    lookback_days: int = 756
    atr_width_multiplier: float = 0.8
    min_zone_width_pct: float = 0.01
    max_zone_width_pct: float = 0.05
    recent_window_days: int = 60
    mid_window_days: int = 180
    volume_baseline_window: int = 20
    reaction_lookahead_days: int = 5
    top_n_per_side: int = 5
    core_zone_threshold: float = 2.0
    invalidation_ma_distance_pct: float = 0.03
    swing_window: int = 5
    cluster_span_multiplier: float = 2.5
    selection_max_distance_pct: float = 0.50
    selection_min_recency_score: float = 3.0
    overlap_min_ratio: float = 0.50
    overlap_center_distance_atr_multiplier: float = 0.50
    overlap_max_last_touch_gap_days: int = 21
    balance_overlap_min_ratio: float = 0.30
    balance_center_distance_atr_multiplier: float = 1.00
    balance_max_last_touch_gap_days: int = 21
    episode_max_gap_days: int = 10
    volume_profile_bin_count: int = 50
    volume_profile_top_k: int = 5
    score_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "touch": 0.35,
            "recency": 0.20,
            "volume": 0.30,
            "confluence": 0.15,
        }
    )


class StructureLevelView(BaseModel):
    """출력용 구조 zone raw payload"""

    lower_bound: float
    upper_bound: float
    mid_price: float
    strength: str
    reasons: list[str] = Field(default_factory=list)
    touch_count: int
    last_touch_date: str | None = None
    total_score: float


class InvalidationLevelView(BaseModel):
    """출력용 구조 무효화 raw payload"""

    label: str
    lower_bound: float
    upper_bound: float
    reference: str | None = None
    reasons: list[str] = Field(default_factory=list)


class StructureLevelsPayloadV2(BaseModel):
    """Composer translated payload (V2)."""

    summary_label: str
    headline: str
    why: str
    active_box: StructureLevelView | None = None
    support_zones: list[StructureLevelView] = Field(default_factory=list)
    resistance_zones: list[StructureLevelView] = Field(default_factory=list)
    former_levels: list[StructureLevelView] = Field(default_factory=list)
    invalidation: InvalidationLevelView | None = None
    patterns_reference: list[str] = Field(default_factory=list)


class StructurePresentationPayload(BaseModel):
    """Presenter output for CLI and LLM."""

    top_judgment: str
    headline: str
    why: str
    cli_blocks: list[str] = Field(default_factory=list)
    llm_context: str
    structure_summary: str = ""
    execution_summary: str = ""


class ExecutionLevelView(BaseModel):
    """실행 레벨 payload"""

    type: str
    description: str
    price: float
    distance_pct: float


class LevelPayload(BaseModel):
    """구조/실행 레벨 합성 payload"""

    structure_levels: StructureLevelsPayloadV2
    execution_levels: list[ExecutionLevelView] = Field(default_factory=list)
    structure_summary: str
    execution_summary: str


class ZoneTestArtifact(BaseModel):
    """회귀 테스트용 structure zone 산출물"""

    schema_version: str
    symbol: str
    csv_path: str
    params: dict
    candidates: list[dict]
    selected_zones: list[dict]
    score_breakdown: list[dict]


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
        """메모리 최적화: OHLCV + 지표 컬럼만 저장"""
        # Flatten MultiIndex columns (yfinance single ticker returns MultiIndex)
        df_copy = df.copy()
        if isinstance(df_copy.columns, pd.MultiIndex):
            df_copy.columns = df_copy.columns.get_level_values(0)

        # Include Volume for charting, plus indicator columns
        base_cols = ["Open", "High", "Low", "Close", "Volume"]
        indicator_cols = [
            col
            for col in df_copy.columns
            if col.startswith(
                (
                    "SMA_",
                    "SuperTrend_",
                    "MACD",
                    "cRSI",
                    "Vol_SMA_",
                    "Is_Stage2",
                    "BB_",
                    "ADX",
                    "ATR",
                    "RSI",
                )
            )
            or col
            in [
                "High_52w",
                "Low_52w",
                "Pivot",
                "S1",
                "R1",
                "Swing_High",
                "Swing_Low",
                "Is_Gap_Up",
                "Is_Gap_Down",
            ]
        ]
        keep_cols = [c for c in base_cols + indicator_cols if c in df_copy.columns]

        slim_df = df_copy[keep_cols].copy()
        return cls(raw_dataframe=slim_df, **kwargs)
