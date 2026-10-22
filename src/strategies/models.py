"""Immutable chart input and coverage models for strategy replay."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from src.storage.canonical import canonical_hash
from src.tools.technical.scorecard_models import DataStatus, Direction, Evidence


def _require_ascending_sessions(sessions: tuple[date, ...], name: str) -> None:
    if any(previous >= current for previous, current in zip(sessions, sessions[1:], strict=False)):
        raise ValueError(f"{name} must be strictly ascending and unique")


class BarFinality(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"


class ChartBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    finality: BarFinality = BarFinality.FINAL


class CoverageManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    requested_start: date
    # Nominal request stays intact when period=2y starts one exchange session later.
    effective_start: date | None = None
    actual_start: date
    actual_end: date
    expected_sessions: tuple[date, ...] = ()
    no_trade_sessions: tuple[date, ...] = ()
    complete: bool
    truncation_reason: str | None = None
    listing_first_session: date | None = None

    @model_validator(mode="after")
    def check_sessions(self) -> CoverageManifest:
        if self.effective_start is not None and not (
            self.requested_start <= self.effective_start <= self.actual_start
        ):
            raise ValueError("effective_start must be between requested_start and actual_start")
        if (
            self.listing_first_session is not None
            and self.listing_first_session != self.actual_start
        ):
            raise ValueError("listing_first_session must equal actual_start")
        _require_ascending_sessions(self.expected_sessions, "expected_sessions")
        _require_ascending_sessions(self.no_trade_sessions, "no_trade_sessions")
        if not set(self.no_trade_sessions).issubset(self.expected_sessions):
            raise ValueError("no_trade_sessions must be a subset of expected_sessions")
        if any(not self.actual_start <= day <= self.actual_end for day in self.no_trade_sessions):
            raise ValueError("no_trade_sessions must be within actual coverage bounds")
        return self


class ChartSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    bars: tuple[ChartBar, ...]
    coverage: CoverageManifest

    @model_validator(mode="after")
    def check_complete_coverage(self) -> ChartSeries:
        sessions = tuple(bar.session_date for bar in self.bars)
        _require_ascending_sessions(sessions, "bars")
        observed = set(sessions)
        if observed.intersection(self.coverage.no_trade_sessions):
            raise ValueError("observed bars and no_trade_sessions must be disjoint")
        if any(
            not self.coverage.actual_start <= day <= self.coverage.actual_end for day in sessions
        ):
            raise ValueError("observed bars must be within actual coverage bounds")
        if self.coverage.complete:
            accounted = observed | set(self.coverage.no_trade_sessions)
            missing = set(self.coverage.expected_sessions) - accounted
            if missing or not self.coverage.expected_sessions:
                raise ValueError("Unaccounted expected sessions in complete coverage")
        return self


class ChartBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_version: str
    ticker: str
    as_of: date
    instrument: ChartSeries
    market: ChartSeries | None = None
    market_ticker: str | None = None
    industry: ChartSeries | None = None
    exchange_sessions: tuple[date, ...]
    bundle_hash: str = ""

    @model_validator(mode="after")
    def set_bundle_hash(self) -> ChartBundle:
        _require_ascending_sessions(self.exchange_sessions, "exchange_sessions")
        if (self.market is None) != (self.market_ticker is None):
            raise ValueError("market_ticker must identify the market series")
        if not self.instrument.bars or self.instrument.bars[-1].session_date != self.as_of:
            raise ValueError("as_of must be the final instrument bar session")
        if any(day > self.as_of for day in self.exchange_sessions):
            raise ValueError("ChartBundle contains future exchange sessions")
        for series in (self.instrument, self.market, self.industry):
            if series is None:
                continue
            if (
                any(bar.session_date > self.as_of for bar in series.bars)
                or series.coverage.actual_end > self.as_of
                or any(day > self.as_of for day in series.coverage.expected_sessions)
                or any(day > self.as_of for day in series.coverage.no_trade_sessions)
            ):
                raise ValueError("ChartBundle contains future series data")
            manifest = series.coverage
            if manifest.complete and manifest.effective_start is not None:
                nominal_sessions = tuple(
                    day
                    for day in self.exchange_sessions
                    if manifest.requested_start <= day <= manifest.actual_end
                )
                if len(nominal_sessions) < 2 or manifest.effective_start != nominal_sessions[1]:
                    raise ValueError(
                        "effective_start may skip only the first requested exchange session"
                    )
        coverage = self.instrument.coverage
        if coverage.complete:
            calendar_start = (
                coverage.listing_first_session
                or coverage.effective_start
                or coverage.requested_start
            )
            calendar_sessions = {
                day
                for day in self.exchange_sessions
                if calendar_start <= day <= coverage.actual_end
            }
            if set(coverage.expected_sessions) != calendar_sessions:
                raise ValueError("Complete instrument coverage must match the exchange calendar")
        payload = self.model_dump(mode="python", exclude={"bundle_hash"})
        digest = canonical_hash("jarvis:chart-bundle:v1", payload)
        if self.bundle_hash and self.bundle_hash != digest:
            raise ValueError("bundle_hash does not match chart content")
        object.__setattr__(self, "bundle_hash", digest)
        return self

    def prefix(self, as_of: date, *, origin: date | None = None) -> ChartBundle:
        from src.strategies.chart_bundle import slice_and_rehash_bundle

        return slice_and_rehash_bundle(self, origin=origin, as_of=as_of)

    def has_complete_coverage(self, start: date, end: date) -> bool:
        manifest = self.instrument.coverage
        return (
            manifest.complete
            and manifest.requested_start <= start
            and manifest.actual_start <= start
            and manifest.actual_end >= end
        )


class EntryIntent(StrEnum):
    ALLOW = "allow"
    WATCH = "watch"
    BLOCK = "block"
    NOT_EVALUATED = "not_evaluated"


class ExitIntent(StrEnum):
    HOLD = "hold"
    REDUCE = "reduce"
    EXIT = "exit"
    NOT_EVALUATED = "not_evaluated"


class ReferenceEntryBasis(StrEnum):
    SIGNAL_CLOSE_ESTIMATE = "signal_close_estimate"
    NEXT_OPEN_ACTUAL = "next_open_actual"


class StructureStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class SignalFinality(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"


class ObservationStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    RESOLVED_TO_SIGNAL = "resolved_to_signal"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class EntryOpportunityStatus(StrEnum):
    ALLOW = "allow"
    WATCH = "watch"
    BLOCK = "block"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    NO_RECENT_SIGNAL = "no_recent_signal"
    NOT_EVALUATED = "not_evaluated"


class ObservationCode(StrEnum):
    PULLBACK_WATCH = "PULLBACK_WATCH"
    POST_OVERHEAT_RECOVERY_WATCH = "POST_OVERHEAT_RECOVERY_WATCH"
    HIGHER_LOW = "HIGHER_LOW"
    HIGHER_HIGH = "HIGHER_HIGH"
    BREAKOUT_RECLAIM = "BREAKOUT_RECLAIM"
    SUPPORT_RECLAIM = "SUPPORT_RECLAIM"
    VOLUME_CONTRACTION = "VOLUME_CONTRACTION"
    UP_VOLUME_EXPANSION = "UP_VOLUME_EXPANSION"
    MOMENTUM_REACCELERATION = "MOMENTUM_REACCELERATION"
    BREAKOUT_LEVEL_BREACH = "BREAKOUT_LEVEL_BREACH"
    SUPPORT_BREAK = "SUPPORT_BREAK"
    PULLBACK_LOW_BREACH = "PULLBACK_LOW_BREACH"
    LOWER_HIGH = "LOWER_HIGH"
    LOWER_LOW = "LOWER_LOW"
    DOWN_VOLUME_EXPANSION = "DOWN_VOLUME_EXPANSION"
    MOMENTUM_DECELERATION = "MOMENTUM_DECELERATION"


class ObservationKind(StrEnum):
    SETUP = "SETUP"
    EVIDENCE = "EVIDENCE"


class ObservationDirection(StrEnum):
    POSITIVE = "POSITIVE"
    RISK = "RISK"
    NEUTRAL = "NEUTRAL"


class ObservationScope(StrEnum):
    ENTRY = "ENTRY"
    POSITION = "POSITION"


class ObservationTemporalType(StrEnum):
    EVENT = "EVENT"
    EPISODE = "EPISODE"


class StrategyObservationEpisode(BaseModel):
    observation_id: str
    ticker: str
    schema_version: str
    parameter_fingerprint: str
    code: ObservationCode
    kind: ObservationKind
    direction: ObservationDirection
    scopes: frozenset[ObservationScope] = Field(min_length=1)
    temporal_type: ObservationTemporalType
    finality: SignalFinality
    started_on: date
    status_as_of: date
    ended_on: date | None
    status: ObservationStatus
    evidence: list[Evidence] = Field(min_length=1)
    source_signal_id: str | None = None
    anchor_id: str | None = None
    anchor_type: str | None = None
    anchor_origin_on: date | None = None
    anchor_origin_price: Decimal | None = None
    pivot_date: date | None = None
    confirmed_on: date | None = None
    source_terminal: bool | None = None
    cycle_id: str | None = None

    @field_serializer("scopes")
    def serialize_scopes(self, scopes: frozenset[ObservationScope]) -> list[str]:
        return sorted(scope.value for scope in scopes)


class StrategySignal(BaseModel):
    signal_id: str
    strategy_id: str
    strategy_version: str
    parameter_set_version: str
    parameter_fingerprint: str
    code: str
    occurred_on: date
    finality: SignalFinality
    direction: Direction | None
    signal_price: Decimal
    evidence: list[Evidence] = Field(min_length=1)
    data_status: DataStatus


class EntrySourceAnchors(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    source_date: date
    source_type: str
    signal_price: Decimal
    atr_at_signal: Decimal | None = None
    breakout_level: Decimal | None = None
    origin_support: Decimal | None = None
    pullback_low: Decimal | None = None
    anchor_finality: SignalFinality
    policy_version: str


class SupportAnchor(BaseModel):
    model_config = ConfigDict(frozen=True)

    anchor_id: str
    anchor_type: Literal["SUPERTREND", "SMA50", "PRIOR_BREAKOUT_LEVEL", "SMA150"]
    is_dynamic: bool
    origin_on: date
    origin_price: Decimal
    current_value: Decimal | None = None
    source_signal_id: str | None = None
    cycle_id: str | None = None


class SupportTestState(BaseModel):
    model_config = ConfigDict(frozen=True)

    anchor: SupportAnchor
    status: Literal["HELD", "SOFT_BREACH", "RECLAIMED", "FAILED"]
    below_count: int = Field(ge=0)
    started_on: date
    status_as_of: date
    ended_on: date | None
    finality: BarFinality
    failure_latched: bool = False
    reclaimed_on: date | None = None


class UpCycleState(BaseModel):
    model_config = ConfigDict(frozen=True)

    cycle_id: str | None = None
    started_on: date | None = None
    status: Literal["INACTIVE", "ACTIVE", "TERMINATED"] = "INACTIVE"
    status_as_of: date | None = None
    terminated_on: date | None = None
    terminal_reason: str | None = None
    confirmation_code: str | None = None
    confirmation_on: date | None = None
    finality: BarFinality
    # status_as_of와 함께 사용해 같은 거래일 restart count 중복 증가를 막는다.
    above_sma150_count: int = Field(default=0, ge=0)


class ObservationSourceContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal: StrategySignal
    anchors: EntrySourceAnchors | None = None
    terminal_status: EntryOpportunityStatus | None = None
    terminal_on: date | None = None
    terminal_reason: str | None = None


class SignalEntryOpportunity(BaseModel):
    evaluation_as_of: date
    finality: SignalFinality
    status: EntryOpportunityStatus
    entry_signal: StrategySignal | None
    invalidated_by: StrategySignal | None
    age_bars: int | None
    signal_price: Decimal | None
    execution_reference_price: Decimal | None
    extension_pct: Decimal | None
    market_regime: str | None
    structure_status: StructureStatus
    evidence: list[Evidence] = Field(min_length=1)
    policy_version: str
    anchors: EntrySourceAnchors | None = None
    terminal_on: date | None = None
    terminal_finality: SignalFinality | None = None


class EntryRiskLevel(StrEnum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"


class EntryShadowState(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["CLEAR", "BREACHED", "RECLAIMED", "FAILURE_CANDIDATE"]
    finality: SignalFinality
    started_on: date | None = None
    breach_bars: int = 0
    consecutive_low_closes: int = 0
    confirmed_status: str | None = None
    confirmed_as_of: date | None = None
    candidate_on: date | None = None
    candidate_finality: SignalFinality | None = None


class EntryRiskFlag(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    finality: SignalFinality
    evidence: list[Evidence] = Field(min_length=1)


class EntryShadowResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_as_of: date
    finality: SignalFinality
    policy_version: str
    parameter_fingerprint: str
    data_status: DataStatus
    reason: str
    risk_level: EntryRiskLevel | None = None
    risk_flags: list[EntryRiskFlag] = Field(default_factory=list)
    breakout_states: dict[str, EntryShadowState] = Field(default_factory=dict)
    pullback_states: dict[str, EntryShadowState] = Field(default_factory=dict)
    anchors: EntrySourceAnchors | None = None


class StrategySignalBundle(BaseModel):
    strategy_id: str
    strategy_version: str
    parameter_set_version: str
    parameter_fingerprint: str
    ticker: str
    as_of: date
    observation_history: list[StrategyObservationEpisode]
    signal_history: list[StrategySignal]
    current_signals: list[StrategySignal]
    entry_opportunity: SignalEntryOpportunity
    data_status: DataStatus
    entry_shadow: EntryShadowResult | None = None
    diagnostic_errors: list[str] = Field(default_factory=list)
    up_cycle: UpCycleState | None = None
    support_tests: list[SupportTestState] | None = None
    pullback_policy_inactive_reason: str | None = None
    observations_enabled: bool | None = None
    observation_parameters: dict[str, Any] | None = None

    @model_validator(mode="after")
    def check_current_signals(self) -> StrategySignalBundle:
        expected = [signal for signal in self.signal_history if signal.occurred_on == self.as_of]
        if self.current_signals != expected:
            raise ValueError("current_signals must equal signals from as_of")
        return self


class EntryOpportunity(BaseModel):
    source_event_id: str
    source_event_code: str
    source_event_date: date
    evaluation_as_of: date
    age_bars: int
    reference_entry: float
    reference_entry_basis: ReferenceEntryBasis
    reference_stop: float
    extension_pct: float
    extension_r: float | None
    extension_atr: float | None
    breakout_distance_pct: float | None
    sma20_distance_pct: float | None
    market_regime: str
    structure_status: StructureStatus
    policy_version: str
    next_open_recheck_required: bool


class StrategyEvent(BaseModel):
    event_id: str
    code: str
    event_version: str
    occurred_on: date
    direction: Direction | None
    evidence: list[Evidence]


class EntryVerdict(BaseModel):
    intent: EntryIntent
    opportunity: EntryOpportunity | None
    data_status: DataStatus
    reasons: list[Evidence]


class ExitVerdict(BaseModel):
    intent: ExitIntent
    data_status: DataStatus
    reasons: list[Evidence]


class StrategyState(BaseModel):
    state_type: str
    state_version: str


class SwingRuntimeState(StrategyState):
    state_type: Literal["swing_w150"]
    lifecycle: Literal["active", "closed"]
    cycle_phase: Literal["signal", "active", "awaiting_rebuy", "closed"]
    kind: Literal["S", "D"] | None
    entry: float | None
    stop: float | None
    risk: float | None
    graduated: bool | None
    overheat_armed: bool | None
    previous_below_exit_line: bool | None


class StrategyVerdict(BaseModel):
    verdict_schema_version: str
    strategy_id: str
    strategy_version: str
    ticker: str
    as_of: date
    entry: EntryVerdict
    exit: ExitVerdict
    events: list[StrategyEvent]
    strategy_state: SwingRuntimeState | None = Field(discriminator="state_type")
