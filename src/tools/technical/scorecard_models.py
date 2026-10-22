"""Typed, versioned explanation of the five technical state dimensions."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class DataStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"
    NOT_EVALUATED = "not_evaluated"


class Direction(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    UNKNOWN = "unknown"


class Acceleration(StrEnum):
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    STABLE = "stable"
    UNKNOWN = "unknown"


class Importance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TriggerStatus(StrEnum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class DirectionalMetric(BaseModel):
    code: str
    value: float | None
    unit: str | None
    direction: Direction
    delta_1d: float | None
    slope: float | None
    slope_unit: str | None
    slope_lookback_bars: int
    acceleration: Acceleration
    calculation_version: str
    data_status: DataStatus
    missing_reason: str | None


class Evidence(BaseModel):
    code: str
    message: str
    observed_value: float | None
    reference_value: float | None
    importance: Importance
    source: str


class Observation(BaseModel):
    code: str
    message: str
    direction: Direction | None
    importance: Importance
    source_metrics: list[str]
    evidence: list[Evidence]


class AnalysisTriggerEvent(BaseModel):
    code: str
    trigger_version: str
    occurred_on: date
    bars_ago: int
    direction: Direction | None
    source: str
    observed_value: float | None
    reference_value: float | None
    status: TriggerStatus
    status_as_of: date
    status_changed_on: date
    status_reason: str
    expires_after_bars: int | None
    invalidated_on: date | None
    expired_on: date | None
    evidence: list[Evidence]


class ScoreContribution(BaseModel):
    rule_code: str
    raw_state: str
    points: int
    required_inputs: list[str]
    missing_inputs: list[str]
    calculation_version: str
    evidence: list[Evidence]


class ScoreDimension(BaseModel):
    code: str
    score: int | None = Field(ge=0, le=100)
    raw_state_points: int | None
    minimum_points: int
    maximum_points: int
    calculation_version: str
    data_status: DataStatus
    coverage_pct: float = Field(ge=0, le=100)
    metrics: dict[str, DirectionalMetric | float | int | str | bool | None]
    observations: list[Observation]
    score_contributions: list[ScoreContribution]


class TechnicalScorecard(BaseModel):
    version: str
    ticker: str
    as_of: date
    trend: ScoreDimension
    structure: ScoreDimension
    momentum: ScoreDimension
    demand: ScoreDimension
    safety: ScoreDimension
    triggers: list[AnalysisTriggerEvent] = Field(default_factory=list)
    legacy_raw_total: int | None
    legacy_adjusted_score: int | None

    def dimensions(self) -> tuple[ScoreDimension, ...]:
        return self.trend, self.structure, self.momentum, self.demand, self.safety
