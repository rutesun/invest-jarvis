from datetime import datetime
from typing import Literal, Self

import pandas as pd
from pydantic import BaseModel, Field, StrictInt, model_validator


SignalType = Literal[
    "breakout",
    "pullback",
    "reversal",
    "breakdown",
    "overextension",
    "support",
    "resistance",
    "trend",
    "volume_confirmation",
]
SignalBias = Literal["bullish", "bearish", "neutral"]
SignalIntent = Literal["entry", "hold", "risk", "watch"]
SignalSeverity = Literal["low", "medium", "high"]
VerdictAction = Literal["buy", "add", "hold", "watch", "reduce", "avoid"]
VerdictConfidence = Literal["low", "medium", "high"]


class ComponentSignal(BaseModel):
    """Structured signal metadata consumed by ScoreAggregator."""

    signal_type: SignalType
    bias: SignalBias
    intent: SignalIntent
    severity: SignalSeverity = "medium"
    entry_eligible: bool = False
    source: str | None = None
    reason: str | None = None


class MarketContext(BaseModel):
    """Derived OHLCV state used for score aggregation."""

    close: float
    close_above_sma20: bool = False
    close_above_sma50: bool = False
    close_above_sma150: bool = False
    close_above_sma200: bool = False
    sma20_above_sma50: bool = False
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_10d: float | None = None
    distance_from_20d_high_pct: float | None = None
    distance_from_sma20_pct: float | None = None
    distance_from_sma50_pct: float | None = None
    volume_ratio_20d: float | None = None
    rsi: float | None = None
    atr_pct: float | None = None
    supertrend_direction: int | None = None
    supertrend_sell_transition: bool = False
    is_overextended: bool = False
    is_breakdown: bool = False
    is_uptrend: bool = False
    is_downtrend: bool = False
    nearest_support: float | None = None


class AggregationTraceEntry(BaseModel):
    """One score adjustment made by ScoreAggregator."""

    rule: str
    before: int
    after: int
    reason: str


class TechnicalVerdict(BaseModel):
    """Technical-only action hint. Playbook remains the final decision layer."""

    action: VerdictAction
    entry_mode: str
    confidence: VerdictConfidence
    new_entry_allowed: bool
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    invalidation_level: float | None = None
    score_trend_summary: str | None = None


class ScoreHistoryPoint(BaseModel):
    """Recent per-day score and verdict summary."""

    date: str
    close: float
    component_raw_total: int
    adjusted_score: int
    verdict_action: VerdictAction
    one_line_reason: str
    new_entry_allowed: bool | None = None
    driver_components: list[str] = Field(default_factory=list)
    change_drivers: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class ComponentResult(BaseModel):
    """Result from a technical analysis component."""

    signals: list[str]
    evidence: list[str]
    metrics: dict[str, float]
    score: StrictInt
    signal_metadata: list[ComponentSignal] = Field(default_factory=list)


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
    sma_100: float | None = None
    sma_120: float | None = None
    sma_150: float | None = None
    sma_200: float | None = None
    sma_20_slope_pct: float | None = None
    sma_50_slope_pct: float | None = None
    sma_100_slope_pct: float | None = None
    sma_150_slope_pct: float | None = None
    sma_200_slope_pct: float | None = None

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

    support_zones: list[StructureZone] = Field(default_factory=list)
    resistance_zones: list[StructureZone] = Field(default_factory=list)
    former_levels: list[StructureZone] = Field(default_factory=list)
    invalidation_candidates: list[StructureZone] = Field(default_factory=list)
    invalidation_zone: StructureZone | None = None
    all_candidates: list[StructureZone] = Field(default_factory=list)
    selection_trace: list[dict[str, object]] = Field(default_factory=list)
    touch_episodes: list[dict[str, object]] = Field(default_factory=list)
    no_clear_structure: bool = False
    no_clear_structure_reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_zone_keys(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        upgraded = dict(data)
        if "support_zones" not in upgraded and "demand_zones" in upgraded:
            upgraded["support_zones"] = upgraded["demand_zones"]
        if "resistance_zones" not in upgraded and "supply_zones" in upgraded:
            upgraded["resistance_zones"] = upgraded["supply_zones"]
        if "former_levels" not in upgraded and "balance_zones" in upgraded:
            upgraded["former_levels"] = upgraded["balance_zones"]
        return upgraded

    @property
    def demand_zones(self) -> list[StructureZone]:
        """Legacy alias for support_zones."""
        return self.support_zones

    @property
    def supply_zones(self) -> list[StructureZone]:
        """Legacy alias for resistance_zones."""
        return self.resistance_zones

    @property
    def balance_zones(self) -> list[StructureZone]:
        """Legacy alias for former_levels."""
        return self.former_levels


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
    component_raw_total: int | None = None
    adjusted_score: int | None = None
    technical_verdict: TechnicalVerdict | None = None
    score_history: list[ScoreHistoryPoint] = Field(default_factory=list)
    score_history_warning: str | None = None
    aggregation_trace: list[AggregationTraceEntry] = Field(default_factory=list)

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

    @model_validator(mode="after")
    def _backfill_score_contract_fields(self) -> Self:
        component_scores = [component.get("score") for component in self.components.values()]
        for component_name, component in self.components.items():
            if "score" in component and type(component["score"]) is not int:
                raise ValueError(f"component score for {component_name} must be an integer")
        if component_scores and all(type(score) is int for score in component_scores):
            component_raw_total = sum(component_scores)
            if self.total_score != component_raw_total:
                raise ValueError("total_score must equal the sum of component scores")
            if (
                self.component_raw_total is not None
                and self.component_raw_total != component_raw_total
            ):
                raise ValueError("component_raw_total must equal the sum of component scores")
            self.component_raw_total = component_raw_total
        elif self.component_raw_total is not None:
            if self.component_raw_total != self.total_score:
                raise ValueError(
                    "component_raw_total must equal total_score when component scores "
                    "cannot be fully computed"
                )
        else:
            self.component_raw_total = self.total_score
        if self.adjusted_score is None:
            self.adjusted_score = self.total_score
        return self

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
