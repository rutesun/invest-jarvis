"""기존 관찰·신호를 읽어 현재 근거와 거래일 흐름을 설명한다."""

from __future__ import annotations

import math
from collections import defaultdict

from src.pipelines.strategy_analysis import AnalysisStrategyResult
from src.pipelines.strategy_render import _OBSERVATION_LABELS
from src.strategies.models import ObservationStatus, ObservationTemporalType, SignalFinality
from src.tools.disclosure import is_korean_ticker
from src.tools.technical.scorecard_models import DataStatus


_ANCHORS = {
    "SMA20": "20일선",
    "SMA50": "50일선",
    "SMA150": "150일선",
    "SMA200": "200일선",
    "SUPERTREND": "Supertrend",
    "PRIOR_BREAKOUT_LEVEL": "돌파 기준",
    "ORIGIN_SUPPORT": "진입 당시 지지선",
    "PULLBACK_LOW": "눌림목 저점",
}
_STRUCTURE = {
    "HIGHER_HIGH": "고점 상승",
    "LOWER_HIGH": "고점 하락",
    "HIGHER_LOW": "저점 상승",
    "LOWER_LOW": "저점 하락",
}
_SIGNALS = {
    "SMA150_EXIT": "150일선 청산 조건 충족",
    "OVERHEAT": "과열 조건 도달",
    "OVERHEAT_CORRECTION": "과열 후 조정",
    "OVERHEAT_RESOLVED": "과열 해소",
    "OVERHEAT_EXPIRED": "과열 관찰 만료",
    "TREND_BREAKOUT_ENTRY": "돌파 진입 조건 충족",
    "PULLBACK_REVERSAL_ENTRY": "눌림목 반등 진입 조건 충족",
    "DEEP_RECOVERY_ENTRY": "조정 후 회복 진입 조건 충족",
    "POST_OVERHEAT_RECOVERY_ENTRY": "과열 조정 후 회복 진입 조건 충족",
}
_BREAKS = {"SUPPORT_BREAK", "BREAKOUT_LEVEL_BREACH", "PULLBACK_LOW_BREACH"}
_RECOVERIES = {"SUPPORT_RECLAIM", "BREAKOUT_RECLAIM"}


def _known(item, day):
    dates = (item.started_on, item.status_as_of, item.confirmed_on, item.ended_on, item.pivot_date)
    return (
        all(value is None or value <= day for value in dates)
        and (item.confirmed_on is None or item.confirmed_on >= item.started_on)
        and (item.ended_on is None or item.ended_on >= item.started_on)
    )


def _current(item, day):
    return (
        _known(item, day)
        and item.temporal_type is ObservationTemporalType.EPISODE
        and item.status is ObservationStatus.ACTIVE
        and item.status_as_of == day
        and item.ended_on is None
        and not item.source_terminal
    )


def _event_day(item):
    return item.confirmed_on or item.started_on


def _context(item):
    if item.code in _STRUCTURE:
        return ("가격 구조", None, None, None)
    if item.code == "POST_OVERHEAT_RECOVERY_WATCH":
        return ("과열", None, item.source_signal_id, item.cycle_id)
    return (
        item.anchor_type or _OBSERVATION_LABELS[item.code],
        item.anchor_id,
        item.source_signal_id,
        item.cycle_id,
    )


def _label(item):
    anchor = _ANCHORS.get(item.anchor_type, "지지선")
    if item.code in _BREAKS:
        return f"{anchor} 이탈"
    if item.code in _RECOVERIES:
        return f"{anchor} 회복 확인"
    return _STRUCTURE.get(item.code, _OBSERVATION_LABELS[item.code])


def _finality(value):
    return "잠정" if value is SignalFinality.PROVISIONAL else "확정"


def _current_finality(item, bundle):
    if bundle.entry_opportunity.finality is SignalFinality.PROVISIONAL:
        return SignalFinality.PROVISIONAL
    return item.finality


def _positive(value):
    return value is not None and math.isfinite(float(value)) and float(value) > 0


def _measurement(item):
    evidence = next((e for e in item.evidence if e.code == item.code + "_CURRENT"), None)
    if evidence is None and item.started_on == item.status_as_of:
        evidence = next((e for e in item.evidence if e.code == item.code), None)
    if evidence is None and item.code == "PULLBACK_WATCH":
        evidence = next(
            (
                e
                for e in item.evidence
                if e.code
                in {
                    "SMA_20",
                    "SMA_50",
                    "SMA_150",
                    "SMA_200",
                    "SuperTrend_Up",
                    "PRIOR_BREAKOUT_LEVEL",
                }
            ),
            None,
        )
    return evidence


def _linked_exit(item, observations, signals, day):
    """신호 발생일과 현재 episode의 연속 근거를 함께 요구한다."""
    if item.code != "SUPPORT_BREAK" or item.anchor_type != "SMA150":
        return None
    # 신호에는 anchor ID가 없으므로 여러 현재 150일선 문맥에 임의 배분하지 않는다.
    active = [
        o
        for o in observations
        if _current(o, day) and o.code == "SUPPORT_BREAK" and o.anchor_type == "SMA150"
    ]
    if len(active) != 1:
        return None
    recoveries = [
        o for o in observations if o.code in _RECOVERIES and _context(o) == _context(item)
    ]
    if any(_event_day(o) >= item.started_on for o in recoveries):
        return None
    candidates = [
        s
        for s in signals
        if s.code == "SMA150_EXIT"
        and item.started_on <= s.occurred_on <= day
        and s.finality is SignalFinality.FINAL
        and s.data_status is DataStatus.COMPLETE
    ]
    return max(candidates, key=lambda s: s.occurred_on, default=None)


def _price_text(analysis, item, unit, *, provisional):
    evidence = _measurement(item)
    if (
        evidence is None
        or not _positive(analysis.current_close)
        or not _positive(evidence.reference_value)
    ):
        return "현재 실측/기준값 미평가"
    close, reference = float(analysis.current_close), float(evidence.reference_value)
    if not _positive(evidence.observed_value):
        return "현재 실측/기준값 미평가"
    price = "현재가격" if provisional else "종가"
    result = f"{price} {unit}{close:,.2f} / 기준 {unit}{reference:,.2f} ({(close / reference - 1) * 100:+.2f}%)"
    if reference > close:
        result += f" · 기준선까지 상승 필요 {(reference / close - 1) * 100:+.2f}%"
    return result


def _current_recovery(item, bundle, analysis):
    """당일 확정 EVENT의 실측만 현재 회복으로 읽는다."""
    day = analysis.scorecard.as_of
    if not (
        item.code in _RECOVERIES
        and item.temporal_type is ObservationTemporalType.EVENT
        and item.status is ObservationStatus.RESOLVED
        and item.started_on == item.status_as_of == _event_day(item) == item.ended_on == day
        and _current_finality(item, bundle) is SignalFinality.FINAL
        and bundle.data_status is DataStatus.COMPLETE
        and not item.source_terminal
    ):
        return False
    evidence = _measurement(item)
    return bool(
        evidence is not None
        and _positive(evidence.observed_value)
        and _positive(evidence.reference_value)
        and _positive(analysis.current_close)
        and float(evidence.observed_value) >= float(evidence.reference_value)
        and analysis.current_close >= float(evidence.reference_value)
    )


def _exit_context_recovered(signal, observations, recovered_contexts):
    # Signal 자체에는 anchor가 없으므로 발생 당시 episode 문맥으로만 연결한다.
    contexts = {
        _context(item)
        for item in observations
        if item.code == "SUPPORT_BREAK"
        and item.anchor_type == "SMA150"
        and item.started_on <= signal.occurred_on
        and (item.ended_on is None or signal.occurred_on <= item.ended_on)
    }
    return bool(contexts) and contexts <= recovered_contexts


def render_observation_story(analysis: AnalysisStrategyResult, *, window: int = 20) -> str:
    """요청 안의 기존 결과만 읽는다. 전략·주문·수량 판단은 만들지 않는다."""
    day = analysis.scorecard.as_of
    if analysis.strategy_run.as_of != day:
        return "### 현재 유효 상태\n\n- 현재 상태 미평가 — 평가일 불일치\n\n### 관찰 흐름\n\n- 평가일 불일치로 흐름 미평가"
    unit = "₩" if is_korean_ticker(analysis.scorecard.ticker) else "$"
    days = sorted({d for d in analysis.exchange_sessions if d <= day})[-max(window, 1) :]
    recent = set(days)
    states, flows = [], []
    for bundle in analysis.strategy_run.signal_bundles:
        owner = bundle.strategy_id
        if bundle.as_of != day:
            states.append(f"- {owner}: 현재 상태 미평가 — 평가일 불일치")
            continue
        observations = [
            o
            for o in bundle.observation_history
            if _known(o, day) and bundle.observations_enabled is not False
        ]
        signals = [s for s in bundle.signal_history if s.occurred_on <= day]
        active = [o for o in observations if _current(o, day)]
        current_recoveries = [
            o
            for o in observations
            if _current_recovery(o, bundle, analysis)
            and not any(_context(item) == _context(o) and item.code in _BREAKS for item in active)
        ]
        origins = {o.observation_id for o in active}
        origins.update(o.observation_id for o in current_recoveries)
        linked = {}
        for item in active:
            label = _ANCHORS.get(item.anchor_type, _label(item))
            evidence = _measurement(item)
            exit_signal = (
                _linked_exit(item, observations, signals, day)
                if bundle.data_status is DataStatus.COMPLETE
                else None
            )
            measured_below = bool(
                evidence is not None
                and _positive(evidence.observed_value)
                and _positive(evidence.reference_value)
                and _positive(analysis.current_close)
                and float(evidence.observed_value) < float(evidence.reference_value)
                and analysis.current_close < float(evidence.reference_value)
            )
            provisional = _current_finality(item, bundle) is SignalFinality.PROVISIONAL
            if item.code in _BREAKS:
                description = "이탈 관찰"
                if provisional:
                    description += " (잠정) · 확정 상태 미평가"
                elif exit_signal is not None and measured_below:
                    description = f"청산 조건 충족 후 미회복 · 조건 충족 {exit_signal.occurred_on}"
                    linked[item.observation_id] = exit_signal
                elif item.anchor_type == "SMA150":
                    description += " · 현재 이탈의 청산 조건 지속 여부 미평가"
                states.append(
                    f"- {label}: {description} · 이탈 시작 {item.started_on} · 현재 확인 {day} ({owner})"
                )
                states.append(f"  - {_price_text(analysis, item, unit, provisional=provisional)}")
            else:
                states.append(
                    f"- {_label(item)} · {item.started_on}부터 · 현재 확인 {day} · {_finality(_current_finality(item, bundle))} ({owner})"
                )
        for item in current_recoveries:
            label = _ANCHORS.get(item.anchor_type, "지지선")
            states.append(f"- {label}: 당일 회복 확인 · {day} · 확정 ({owner})")
            states.append(f"  - {_price_text(analysis, item, unit, provisional=False)}")
        # 고점·저점은 각각 마지막 확인을 읽는다. 마지막 이벤트 하나로 구조 전체를 덮지 않는다.
        structural = []
        for codes in ({"HIGHER_LOW", "LOWER_LOW"}, {"HIGHER_HIGH", "LOWER_HIGH"}):
            item = max((o for o in observations if o.code in codes), key=_event_day, default=None)
            if item is not None:
                origins.add(item.observation_id)
                structural.append(
                    f"{_label(item)} 확인 {_event_day(item)} ({_finality(item.finality)})"
                )
        if structural:
            states.append(f"- 가격 구조 ({owner}): " + " · ".join(structural))
        overheat = [s for s in signals if s.code.startswith("OVERHEAT")]
        if overheat:
            last = max(overheat, key=lambda s: s.occurred_on)
            states.append(
                f"- 과열 ({owner}): 최근 {_SIGNALS.get(last.code, last.code)} {last.occurred_on} ({_finality(last.finality)}) · 이후 지속 여부 미평가"
            )
        recovered_contexts = {_context(item) for item in current_recoveries}
        if not linked and any(
            s.code == "SMA150_EXIT"
            and not _exit_context_recovered(s, observations, recovered_contexts)
            for s in signals
        ):
            states.append(
                f"- {owner}: 현재 청산 조건 지속 여부 미평가 — 현재 이탈 구간·연결 신호·실측을 함께 확인할 수 없습니다."
            )
        elif not active and not current_recoveries and not structural and not overheat:
            states.append(f"- {owner}: 현재 관찰 상태 미평가 — 현재 유효 기록 없음")
        if bundle.observations_enabled is False:
            states.append(f"- {owner}: 관찰 비활성 · 현재 상태 미평가")
        elif any(
            o.status is ObservationStatus.ACTIVE
            and o.temporal_type is ObservationTemporalType.EPISODE
            and not _current(o, day)
            for o in bundle.observation_history
            if not o.source_terminal
        ):
            states.append(
                f"- {owner}: 평가일 불일치·미래 기록은 현재 상태 근거에서 제외했습니다 (미평가)."
            )

        groups = defaultdict(list)
        recoveries = {(_context(o), _event_day(o)) for o in observations if o.code in _RECOVERIES}

        def add(context, event_day, text, *, required=False, groups=groups):
            if event_day not in recent and not required:
                return
            suffix = " · 기간 밖 현재 상태 근거" if event_day not in recent else ""
            groups[context].append((event_day, text + suffix))

        for item in observations:
            context = _context(item)
            required = item.observation_id in origins
            if item.temporal_type is ObservationTemporalType.EVENT:
                text = _label(item)
                if not text.endswith("확인"):
                    text += " 확인"
                text += f" · 발생일 {item.started_on} · 확인일 {_event_day(item)} · {_finality(item.finality)}"
                if item.pivot_date is not None:
                    pivot = "고점일" if item.code in {"HIGHER_HIGH", "LOWER_HIGH"} else "저점일"
                    text += f" · {pivot} {item.pivot_date}"
                add(context, _event_day(item), text, required=required)
            else:
                add(
                    context,
                    item.started_on,
                    f"{_label(item)} 관찰 시작 ({_finality(item.finality)})",
                    required=required,
                )
                if item.ended_on is not None and not (
                    item.code in _BREAKS
                    and item.status is ObservationStatus.RESOLVED
                    and (context, item.ended_on) in recoveries
                ):
                    end = {
                        ObservationStatus.RESOLVED: "관찰 종료",
                        ObservationStatus.RESOLVED_TO_SIGNAL: "전략 신호로 전환",
                        ObservationStatus.INVALIDATED: "전제 무효",
                        ObservationStatus.EXPIRED: "기간 만료",
                    }.get(item.status, "관찰 종료")
                    add(
                        context, item.ended_on, f"{_label(item)} {end} ({_finality(item.finality)})"
                    )
                if item in active:
                    add(
                        context,
                        day,
                        f"{_label(item)} · 현재 확인 ({_finality(_current_finality(item, bundle))})",
                        required=True,
                    )
        for signal in signals:
            linked_item = next((o for o in active if linked.get(o.observation_id) == signal), None)
            if signal.code == "SMA150_EXIT":
                matching = [
                    o
                    for o in observations
                    if o.code == "SUPPORT_BREAK"
                    and o.anchor_type == "SMA150"
                    and o.started_on <= signal.occurred_on
                    and (o.ended_on is None or signal.occurred_on <= o.ended_on)
                ]
                context = (
                    _context(linked_item or max(matching, key=lambda o: o.started_on))
                    if linked_item or matching
                    else ("SMA150", None, None, None)
                )
            else:
                context = (
                    "과열" if signal.code.startswith("OVERHEAT") else "진입 신호",
                    None,
                    None,
                    None,
                )
            label = _SIGNALS.get(signal.code, signal.code)
            if signal.code == "SMA150_EXIT":
                count = next(
                    (e for e in signal.evidence if e.code == "CONSECUTIVE_BELOW_SMA150"), None
                )
                if count is not None and _positive(count.observed_value):
                    label = f"{count.observed_value:g}회 연속 종가 이탈 → {label}"
            add(
                context,
                signal.occurred_on,
                f"{label} · 신호 발생일 {signal.occurred_on} ({_finality(signal.finality)})",
                required=linked_item is not None,
            )
        contexts = sorted(groups.items(), key=lambda pair: str(pair[0]))
        titles = [_ANCHORS.get(context[0], context[0]) for context, _ in contexts]
        for number, (context, entries) in enumerate(contexts, 1):
            title = _ANCHORS.get(context[0], context[0])
            identity = f" · 기준 {number}" if titles.count(title) > 1 else ""
            flows += ["", f"#### {owner} · {title}{identity}", ""]
            flows += [f"- {event_day}: {text}" for event_day, text in sorted(set(entries))]
    if not states:
        states = ["- 현재 관찰 미평가 — Strategy bundle 없음"]
    lines = [
        "### 현재 유효 상태",
        "",
        *states,
        "",
        "- 과거 조건 충족은 실행 기록과 구분합니다. 오늘 매매 수량은 전략별 기존 계획을 확인합니다.",
        "",
        "### 관찰 흐름",
        "",
        f"최근 {max(window, 1)}개 반환 거래일의 관찰·신호와 현재 상태의 근원 사건입니다.",
    ]
    if not days:
        lines.append("- 반환 거래일 정보 없음 — 기간 내 이력 미평가")
    return "\n".join(
        [*lines, *(flows or ["", "- 기간 내 관찰·신호 기록 없음 — 미평가 항목은 현재 상태 참조"])]
    )
