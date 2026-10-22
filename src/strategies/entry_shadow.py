"""Independent chart-prefix research diagnostics; never an entry/exit policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from src.storage.canonical import canonical_hash
from src.strategies.models import (
    BarFinality,
    ChartBundle,
    EntryRiskFlag,
    EntryRiskLevel,
    EntryShadowResult,
    EntryShadowState,
    SignalEntryOpportunity,
    SignalFinality,
)
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


POLICY_VERSION = "WATCH_RECLAIM_SHADOW_V1"
_SUPPORTED = {"TREND_BREAKOUT_ENTRY", "PULLBACK_REVERSAL_ENTRY"}


@dataclass(frozen=True)
class EntryShadowParameters:
    """Unvalidated research hypotheses, deliberately outside Production parameters."""

    adverse_atr_multiple: Decimal = Decimal("3")
    initial_bars: int = 5
    low_failure_closes: int = 2

    def __post_init__(self) -> None:
        multiple = Decimal(str(self.adverse_atr_multiple))
        if not multiple.is_finite() or multiple <= 0:
            raise ValueError("adverse_atr_multiple must be positive and finite")
        if (
            not isinstance(self.initial_bars, int)
            or not isinstance(self.low_failure_closes, int)
            or self.initial_bars < 1
            or self.low_failure_closes < 1
        ):
            raise ValueError("research bar counts must be positive integers")
        object.__setattr__(self, "adverse_atr_multiple", multiple)

    @property
    def parameter_fingerprint(self) -> str:
        return canonical_hash("jarvis:entry-shadow-parameters:v1", asdict(self))


@dataclass
class _Episode:
    status: str = "CLEAR"
    started_on: date | None = None
    breach_bars: int = 0
    low_closes: int = 0
    confirmed_status: str | None = None
    confirmed_as_of: date | None = None
    candidate_on: date | None = None
    candidate_close: Decimal | None = None
    candidate_finality: SignalFinality | None = None

    def step(self, day: date, breached: bool, *, can_start: bool = True) -> None:
        if not breached:
            if self.started_on is not None:
                self.status = "RECLAIMED"
            self.started_on = None
            self.breach_bars = self.low_closes = 0
            self.candidate_on = self.candidate_close = self.candidate_finality = None
        elif self.started_on is not None or can_start:
            self.started_on = self.started_on or day
            self.breach_bars += 1
            self.status = "BREACHED"

    def snapshot(self, finality: SignalFinality) -> EntryShadowState:
        return EntryShadowState(
            status=self.status,
            finality=finality,
            started_on=self.started_on,
            breach_bars=self.breach_bars,
            consecutive_low_closes=self.low_closes,
            confirmed_status=self.confirmed_status,
            confirmed_as_of=self.confirmed_as_of,
            candidate_on=self.candidate_on,
            candidate_finality=self.candidate_finality,
        )


def _positive(value: Decimal | None) -> bool:
    return value is not None and value.is_finite() and value > 0


def evaluate_entry_shadow(
    opportunity: SignalEntryOpportunity,
    bundle: ChartBundle,
    *,
    params: EntryShadowParameters | None = None,
) -> EntryShadowResult:
    """Replay source-bounded chart bars without inspecting eligibility or future outcomes."""
    parameters = params or EntryShadowParameters()
    anchors = opportunity.anchors
    source = opportunity.entry_signal
    bars = bundle.instrument.bars
    finality = SignalFinality(bars[-1].finality.value)

    def result(reason: str, **values) -> EntryShadowResult:
        return EntryShadowResult(
            evaluation_as_of=bundle.as_of,
            finality=finality,
            policy_version=POLICY_VERSION,
            parameter_fingerprint=parameters.parameter_fingerprint,
            data_status=DataStatus.NOT_EVALUATED if reason != "EVALUATED" else DataStatus.COMPLETE,
            reason=reason,
            anchors=anchors,
            **values,
        )

    if source is None:
        return result("NO_SOURCE")
    if source.code not in _SUPPORTED:
        return result("UNSUPPORTED_SOURCE")
    if anchors is None:
        return result("MISSING_ANCHORS")
    if (
        anchors.source_id != source.signal_id
        or anchors.source_date != source.occurred_on
        or anchors.source_type != source.code
        or anchors.signal_price != source.signal_price
    ):
        return result("ANCHOR_SOURCE_MISMATCH")
    if anchors.anchor_finality is SignalFinality.PROVISIONAL:
        finality = SignalFinality.PROVISIONAL
    source_bars = tuple(bar for bar in bars if bar.session_date >= anchors.source_date)
    if not source_bars or source_bars[0].session_date != anchors.source_date:
        return result("SOURCE_NOT_IN_CHART")
    if not bundle.has_complete_coverage(anchors.source_date, bundle.as_of):
        return result("INCOMPLETE_CHART_COVERAGE")
    breakout = source.code == "TREND_BREAKOUT_ENTRY"
    required = (
        (("BREAKOUT_LEVEL", anchors.breakout_level), ("ATR_AT_SIGNAL", anchors.atr_at_signal))
        if breakout
        else (("ORIGIN_SUPPORT", anchors.origin_support), ("PULLBACK_LOW", anchors.pullback_low))
    )
    for name, value in required:
        if not _positive(value):
            return result(f"MISSING_{name}")

    rules = {rule: _Episode() for rule in (("B1", "B4") if breakout else ("P1", "P2", "P3"))}
    low_episode = _Episode()
    confirmed = anchors.anchor_finality is SignalFinality.FINAL
    adverse_level = (
        anchors.signal_price - parameters.adverse_atr_multiple * anchors.atr_at_signal
        if breakout
        else None
    )
    for age, bar in enumerate(source_bars):
        confirmed = confirmed and bar.finality is BarFinality.FINAL
        if not confirmed:
            finality = SignalFinality.PROVISIONAL
        if age > 0:
            close = bar.close
            if breakout:
                breach = close < anchors.breakout_level
                rules["B1"].step(bar.session_date, breach)
                early = rules["B4"]
                early.step(bar.session_date, breach, can_start=age <= parameters.initial_bars)
                if (
                    early.started_on is not None
                    and age <= parameters.initial_bars
                    and close <= adverse_level
                    and early.candidate_on is None
                ):
                    early.candidate_on = bar.session_date
                    early.candidate_close = close
                    early.candidate_finality = (
                        SignalFinality.FINAL if confirmed else SignalFinality.PROVISIONAL
                    )
                if early.candidate_on is not None:
                    early.status = "FAILURE_CANDIDATE"
            else:
                support_breach = close < anchors.origin_support
                low_breach = close < anchors.pullback_low
                rules["P1"].step(bar.session_date, support_breach)
                rules["P2"].step(bar.session_date, support_breach)
                if rules["P2"].started_on is not None and low_breach:
                    rules["P2"].status = "FAILURE_CANDIDATE"
                repeated = rules["P3"]
                repeated.step(
                    bar.session_date, close < max(anchors.origin_support, anchors.pullback_low)
                )
                repeated.low_closes = repeated.low_closes + 1 if low_breach else 0
                if repeated.low_closes >= parameters.low_failure_closes:
                    repeated.status = "FAILURE_CANDIDATE"
                low_episode.step(bar.session_date, low_breach)
        if confirmed:
            for episode in rules.values():
                episode.confirmed_status = episode.status
                episode.confirmed_as_of = bar.session_date

    flags = []

    def flag(
        code: str,
        message: str,
        level: Decimal,
        *,
        high: bool = False,
        observed: Decimal | None = None,
        flag_finality: SignalFinality | None = None,
    ) -> None:
        flags.append(
            EntryRiskFlag(
                code=code,
                message=message,
                finality=flag_finality or finality,
                evidence=[
                    Evidence(
                        code=code,
                        message=message,
                        observed_value=float(observed if observed is not None else bars[-1].close),
                        reference_value=float(level),
                        importance=Importance.HIGH if high else Importance.MEDIUM,
                        source=POLICY_VERSION,
                    )
                ],
            )
        )

    def structure_flags(episode: _Episode, prefix: str, label: str, level: Decimal) -> None:
        if episode.started_on is not None:
            flag(f"{prefix}_BREACH", f"{label} 이탈", level)
        elif episode.status == "RECLAIMED":
            flag(f"{prefix}_RECLAIMED", f"{label} 회복", level)

    high_risk = False
    if breakout:
        structure_flags(rules["B1"], "BREAKOUT_LEVEL", "돌파 기준선", anchors.breakout_level)
        if len(source_bars) > 1 and bars[-1].close <= adverse_level:
            high_risk = True
            flag("LARGE_ADVERSE_MOVE", "Signal 당시 ATR 대비 큰 하락", adverse_level, high=True)
        if rules["B4"].status == "FAILURE_CANDIDATE":
            high_risk = True
            early = rules["B4"]
            flag(
                "EARLY_FAILED_BREAKOUT_CANDIDATE",
                "초기 돌파 실패 관측 후 기준선 미회복",
                adverse_level,
                high=True,
                observed=early.candidate_close,
                flag_finality=early.candidate_finality,
            )
    else:
        structure_flags(rules["P1"], "ORIGIN_SUPPORT", "최초 지지선", anchors.origin_support)
        structure_flags(low_episode, "PULLBACK_LOW", "조정 저점", anchors.pullback_low)
        high_risk = (
            low_episode.started_on is not None
            or rules["P2"].status == "FAILURE_CANDIDATE"
            or rules["P3"].status == "FAILURE_CANDIDATE"
        )
        if rules["P2"].status == "FAILURE_CANDIDATE" or rules["P3"].status == "FAILURE_CANDIDATE":
            flag(
                "SEVERE_PULLBACK_DETERIORATION",
                "조정 구조의 심한 악화 후보",
                anchors.pullback_low,
                high=True,
            )
    risk = (
        EntryRiskLevel.HIGH_RISK
        if high_risk
        else EntryRiskLevel.CAUTION
        if any(episode.started_on is not None for episode in rules.values())
        else EntryRiskLevel.NORMAL
    )
    states = {rule: episode.snapshot(finality) for rule, episode in rules.items()}
    return result(
        "EVALUATED",
        risk_level=risk,
        risk_flags=flags,
        breakout_states=states if breakout else {},
        pullback_states={} if breakout else states,
    )
