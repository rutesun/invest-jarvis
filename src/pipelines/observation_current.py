"""기존 관찰 판정을 HTML의 현재 상태와 문맥별 경과로 투영한다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite

from src.pipelines.observation_story import (
    _ANCHORS,
    _BREAKS,
    _RECOVERIES,
    _SIGNALS,
    _STRUCTURE,
    _context,
    _current,
    _current_finality,
    _current_recovery,
    _event_day,
    _exit_context_recovered,
    _known,
    _label,
    _linked_exit,
    _measurement,
    _positive,
)
from src.pipelines.strategy_analysis import AnalysisStrategyResult
from src.strategies.models import ObservationStatus, ObservationTemporalType, SignalFinality
from src.tools.technical.scorecard_models import DataStatus


@dataclass(frozen=True)
class ObservationHistoryEntry:
    day: date
    text: str
    source_id: str
    finality: SignalFinality = SignalFinality.FINAL


@dataclass(frozen=True)
class CurrentObservation:
    strategy_id: str
    context: tuple[str | None, ...]
    title: str
    measurement: str = ""
    next_check: str | None = None
    history: tuple[ObservationHistoryEntry, ...] = ()
    importance: int = 30
    finality: SignalFinality = SignalFinality.FINAL
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CurrentObservationSummary:
    as_of: date
    finality: SignalFinality
    states: tuple[CurrentObservation, ...] = ()
    warnings: tuple[str, ...] = ()


def _history(observations, context, *, signal=None, sources=()):
    """기간 밖 근원도 보존하되 다른 anchor/source/cycle을 섞지 않는다."""
    related = [item for item in observations if _context(item) == context]
    recoveries = {
        (_context(item), _event_day(item)) for item in related if item.code in _RECOVERIES
    }
    rows = []
    for item in related:
        label = _label(item)
        if item.temporal_type is ObservationTemporalType.EVENT:
            text = label if label.endswith("확인") else label + " 확인"
            if item.pivot_date is not None:
                text += f" · {'고점일' if item.code in {'HIGHER_HIGH', 'LOWER_HIGH'} else '저점일'} {item.pivot_date}"
            rows.append(
                ObservationHistoryEntry(_event_day(item), text, item.observation_id, item.finality)
            )
        else:
            rows.append(
                ObservationHistoryEntry(
                    item.started_on, label + " 관찰 시작", item.observation_id, item.finality
                )
            )
            if item.ended_on is not None and not (
                item.code in _BREAKS
                and item.status is ObservationStatus.RESOLVED
                and (context, item.ended_on) in recoveries
            ):
                end = {
                    ObservationStatus.RESOLVED_TO_SIGNAL: "전략 신호로 전환",
                    ObservationStatus.INVALIDATED: "전제 무효",
                    ObservationStatus.EXPIRED: "기간 만료",
                }.get(item.status, "관찰 종료")
                rows.append(
                    ObservationHistoryEntry(
                        item.ended_on, f"{label} {end}", item.observation_id, item.finality
                    )
                )
    source_signals = [source for source in sources if source.signal_id == context[2]]
    if signal is not None:
        source_signals.append(signal)
    for signal in source_signals:
        count = next((e for e in signal.evidence if e.code == "CONSECUTIVE_BELOW_SMA150"), None)
        prefix = (
            f"{count.observed_value:g}회 연속 종가 이탈 → "
            if count and _positive(count.observed_value)
            else ""
        )
        rows.append(
            ObservationHistoryEntry(
                signal.occurred_on,
                prefix + _SIGNALS.get(signal.code, signal.code),
                signal.signal_id,
                signal.finality,
            )
        )
    return tuple(sorted(set(rows), key=lambda row: (row.day, row.source_id, row.text)))


_PRICE_OBSERVATIONS = _BREAKS | _RECOVERIES | {"PULLBACK_WATCH"}


def _measurement_ready(item):
    evidence = _measurement(item)
    if evidence is None:
        return False
    values = (evidence.observed_value, evidence.reference_value)
    if item.code in _PRICE_OBSERVATIONS | {"MOMENTUM_DECELERATION"}:
        return all(_positive(value) for value in values)
    # slope 등의 비가격 근거는 0·음수가 유효하다. 금융 조건은 원래 detector가 판정한다.
    return all(value is not None and isfinite(float(value)) for value in values)


def _distance(analysis, item):
    if not _measurement_ready(item):
        return "현재 실측/기준값 미평가"
    if item.code not in _PRICE_OBSERVATIONS:
        return ""  # 비가격 지표를 주가와의 거리로 해석하지 않는다.
    if not _positive(analysis.current_close):
        return "현재 실측/기준값 미평가"
    evidence = _measurement(item)
    reference, close = float(evidence.reference_value), float(analysis.current_close)
    distance = (close / reference - 1) * 100
    label = _ANCHORS.get(item.anchor_type, "기준선")
    direction = "위" if distance > 0 else "아래" if distance < 0 else "동일"
    return f"주가는 {label}보다 {distance:+.2f}% {direction}"


def build_current_observations(analysis: AnalysisStrategyResult) -> CurrentObservationSummary:
    """전략 payload를 변경하지 않고 이미 평가된 현재 사실만 읽는다."""
    day, run = analysis.scorecard.as_of, analysis.strategy_run
    provisional = any(
        bundle.as_of == day and bundle.entry_opportunity.finality is SignalFinality.PROVISIONAL
        for bundle in run.signal_bundles
    )
    finality = SignalFinality.PROVISIONAL if provisional else SignalFinality.FINAL
    if run.as_of != day:
        return CurrentObservationSummary(
            day, finality, warnings=("현재 상태 미평가 — 평가일 불일치",)
        )
    states, warnings = [], []
    if not any(session <= day for session in analysis.exchange_sessions):
        warnings.append("반환 거래일 정보 없음 — 경과 기간 미평가")
    for bundle in run.signal_bundles:
        owner = bundle.strategy_id
        bundle_provisional = bundle.entry_opportunity.finality is SignalFinality.PROVISIONAL
        if bundle.as_of != day:
            warnings.append(f"{owner}: 현재 상태 미평가 — 평가일 불일치")
            continue
        observations = [
            item
            for item in bundle.observation_history
            if _known(item, day) and bundle.observations_enabled is not False
        ]
        signals = [
            signal
            for signal in bundle.signal_history
            if signal.occurred_on <= day and signal.strategy_id == owner
        ]
        active = [item for item in observations if _current(item, day)]
        recoveries = [
            item
            for item in observations
            if _current_recovery(item, bundle, analysis)
            and not any(
                _context(other) == _context(item) and other.code in _BREAKS for other in active
            )
        ]
        linked = []
        count_before = len(states)
        for item in [*recoveries, *active]:
            state_finality = _current_finality(item, bundle)
            measurement = _distance(analysis, item)
            label = _ANCHORS.get(item.anchor_type, _label(item))
            issues = []
            next_check = None
            signal = (
                _linked_exit(item, observations, signals, day)
                if bundle.data_status is DataStatus.COMPLETE
                else None
            )
            evidence = _measurement(item)
            measured_below = bool(
                evidence
                and all(
                    _positive(value)
                    for value in (
                        analysis.current_close,
                        evidence.observed_value,
                        evidence.reference_value,
                    )
                )
                and evidence.observed_value < evidence.reference_value
                and analysis.current_close < evidence.reference_value
            )
            if item in recoveries:
                title, importance = f"{label}: 당일 회복 확인", 10
            elif item.code in _BREAKS:
                title, importance = f"{label} 이탈 관찰", 20
                next_check = f"{label} 회복 여부"
                if state_finality is SignalFinality.FINAL and signal is not None and measured_below:
                    title, importance = f"{label} 청산 조건 충족 후 미회복", 0
                    linked.append(signal.signal_id)
                elif item.anchor_type == "SMA150":
                    issues.append("청산 상태 확인 불가 — 현재 이탈 구간·연결 신호·실측 확인 필요")
            else:
                title, importance = _label(item), 30
            if state_finality is SignalFinality.PROVISIONAL:
                issues.append("장중 잠정 · 확정 상태 미평가")
            if bundle.data_status is not DataStatus.COMPLETE:
                issues.append("데이터 불완전 · 현재 상태 확정 미평가")
            if "미평가" in measurement:
                issues.append(measurement)
            scoped = tuple(f"{owner} · {title}: {issue}" for issue in issues)
            warnings.extend(scoped)
            history = list(
                _history(
                    observations,
                    _context(item),
                    signal=signal if signal and signal.signal_id in linked else None,
                    sources=signals,
                )
            )
            if item not in recoveries:
                history.append(
                    ObservationHistoryEntry(
                        day, _label(item) + " · 현재 확인", item.observation_id, state_finality
                    )
                )
            states.append(
                CurrentObservation(
                    owner,
                    _context(item),
                    title,
                    measurement,
                    next_check,
                    tuple(sorted(history, key=lambda row: (row.day, row.source_id, row.text))),
                    importance,
                    state_finality,
                    scoped,
                )
            )
        structural = []
        for codes in ({"HIGHER_HIGH", "LOWER_HIGH"}, {"HIGHER_LOW", "LOWER_LOW"}):
            item = max(
                (item for item in observations if item.code in codes), key=_event_day, default=None
            )
            if item is not None:
                structural.append(item)
        if structural:
            state_finality = (
                SignalFinality.PROVISIONAL
                if any(item.finality is SignalFinality.PROVISIONAL for item in structural)
                else SignalFinality.FINAL
            )
            issues = (
                (f"{owner} · 가격 구조: 잠정 근거 포함 · 확정 구조 미평가",)
                if state_finality is SignalFinality.PROVISIONAL
                else ()
            )
            if bundle.data_status is not DataStatus.COMPLETE:
                issues += (f"{owner} · 가격 구조: 데이터 불완전 · 현재 상태 확정 미평가",)
            warnings.extend(issues)
            states.append(
                CurrentObservation(
                    owner,
                    ("가격 구조", None, None, None),
                    "최근 확인된 " + " · ".join(_label(item) for item in structural),
                    history=_history(observations, ("가격 구조", None, None, None)),
                    importance=25,
                    finality=state_finality,
                    warnings=issues,
                )
            )
        # 확정 회복에서 제외된 당일 후보도 잠정·실측 부족을 현재 화면에 남긴다.
        for item in observations:
            if (
                item.code not in _RECOVERIES
                or item.temporal_type is not ObservationTemporalType.EVENT
                or _event_day(item) != day
                or item.source_terminal
                or item in recoveries
            ):
                continue
            state_finality = _current_finality(item, bundle)
            title = f"{_ANCHORS.get(item.anchor_type, '기준선')} 회복 미평가"
            reason = "잠정 근거 · " if state_finality is SignalFinality.PROVISIONAL else ""
            issues = (
                f"{owner} · {title}: 당일 회복 미평가 — {reason}현재 평가일·실측·이탈 문맥 확인 필요",
            )
            warnings.extend(issues)
            states.append(
                CurrentObservation(
                    owner,
                    _context(item),
                    title,
                    history=_history(observations, _context(item), sources=signals),
                    importance=10,
                    finality=state_finality,
                    warnings=issues,
                )
            )
        # 당일 EVENT/신호는 확정·완전한 입력일 때만 새 변화로 노출한다.
        for item in observations:
            if (
                item.code in _STRUCTURE
                or item.code in _RECOVERIES
                or item.temporal_type is not ObservationTemporalType.EVENT
                or _event_day(item) != day
            ):
                continue
            current_event = (
                item.status_as_of == day
                and item.status is ObservationStatus.RESOLVED
                and item.ended_on == day
                and not item.source_terminal
            )
            if current_event and item.finality is SignalFinality.PROVISIONAL:
                finality = SignalFinality.PROVISIONAL
            if (
                not current_event
                or item.finality is not SignalFinality.FINAL
                or bundle_provisional
                or bundle.data_status is not DataStatus.COMPLETE
                or not _measurement_ready(item)
            ):
                warnings.append(
                    f"{owner} · {_label(item)}: 당일 변화 미평가 — 잠정 또는 실측·평가일 확인 필요"
                )
                continue
            states.append(
                CurrentObservation(
                    owner,
                    _context(item),
                    _label(item) + " · 당일 확인",
                    history=_history(observations, _context(item)),
                    importance=30,
                )
            )
        for signal in signals:
            if signal.occurred_on != day or signal.signal_id in linked:
                continue
            label = _SIGNALS.get(signal.code, signal.code)
            if signal.finality is SignalFinality.PROVISIONAL:
                finality = SignalFinality.PROVISIONAL
            if (
                signal.finality is not SignalFinality.FINAL
                or bundle_provisional
                or signal.data_status is not DataStatus.COMPLETE
                or not _positive(signal.signal_price)
                or bundle.data_status is not DataStatus.COMPLETE
            ):
                warnings.append(f"{owner} · {label}: 당일 변화 잠정·데이터 미평가")
                continue
            states.append(
                CurrentObservation(
                    owner,
                    ("신호", signal.signal_id, None, None),
                    label + " · 당일 신호",
                    history=(
                        ObservationHistoryEntry(day, label, signal.signal_id, signal.finality),
                    ),
                    importance=15,
                )
            )
        recovered_contexts = {_context(item) for item in recoveries}
        if (
            not linked
            and not any(
                warning.startswith(owner + " · ") and "청산 상태 확인 불가" in warning
                for warning in warnings
            )
            and any(
                signal.code == "SMA150_EXIT"
                and not _exit_context_recovered(signal, observations, recovered_contexts)
                for signal in signals
            )
        ):
            warnings.append(
                f"{owner}: 청산 상태 확인 불가 — 현재 이탈 구간·연결 신호·실측 확인 필요"
            )
        if bundle.observations_enabled is False:
            warnings.append(f"{owner}: 관찰 비활성 · 현재 상태 미평가")
        elif any(
            item.status is ObservationStatus.ACTIVE
            and item.temporal_type is ObservationTemporalType.EPISODE
            and not _current(item, day)
            and not item.source_terminal
            for item in bundle.observation_history
        ):
            warnings.append(f"{owner}: 평가일 불일치·미래 기록 제외 · 현재 상태 미평가")
        if len(states) == count_before:
            warnings.append(f"{owner}: 현재 관찰 상태 미평가 — 현재 유효 기록 없음")
    if not run.signal_bundles:
        warnings.append("현재 관찰 미평가 — Strategy bundle 없음")
    return CurrentObservationSummary(
        day,
        SignalFinality.PROVISIONAL
        if any(state.finality is SignalFinality.PROVISIONAL for state in states)
        else finality,
        tuple(sorted(states, key=lambda item: item.importance)),
        tuple(dict.fromkeys(warnings)),
    )
