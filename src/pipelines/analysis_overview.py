"""기존 계산을 읽기만 하는 현재 상태·가격 경계·5거래일 공통 표시."""

from __future__ import annotations

import math

from src.pipelines.observation_story import render_observation_story
from src.pipelines.quality_overview import (
    finality as quality_finality,
)
from src.pipelines.quality_overview import (
    quality_cell,
    quality_change_lines,
    quality_close,
    quality_history_by_day,
    render_quality_overview,
    valid_result,
)
from src.pipelines.strategy_analysis import AnalysisStrategyResult
from src.pipelines.strategy_render import (
    _OBSERVATION_LABELS,
    _decision_evidence_lines,
    _observation_evaluation_lines,
    _opportunity_reason,
    render_strategy_sections,
)
from src.strategies.models import (
    EntryOpportunityStatus,
    ObservationStatus,
    ObservationTemporalType,
    SignalFinality,
)
from src.tools.disclosure import is_korean_ticker
from src.tools.technical.scorecard_models import TechnicalScorecard


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
_SIGNALS = {
    "TREND_BREAKOUT_ENTRY": "돌파 진입 조건 충족",
    "PULLBACK_REVERSAL_ENTRY": "눌림목 반등 진입 조건 충족",
    "DEEP_RECOVERY_ENTRY": "조정 후 회복 진입 조건 충족",
    "POST_OVERHEAT_RECOVERY_ENTRY": "과열 조정 후 회복 진입 조건 충족",
    "SMA150_EXIT": "150일선 청산 조건 충족",
    "OVERHEAT": "과열 조건 도달",
    "OVERHEAT_CORRECTION": "과열 후 조정",
    "OVERHEAT_RESOLVED": "과열 해소",
    "OVERHEAT_EXPIRED": "과열 관찰 만료",
}
_ENTRY = {"allow": "진입 가능", "watch": "대기", "block": "진입 제한", "not_evaluated": "미평가"}
_EXIT = {"hold": "보유", "reduce": "일부 축소", "exit": "청산", "not_evaluated": "미평가"}
_SUPPORT_EVIDENCE = {
    "SMA_20": "SMA20",
    "SMA_50": "SMA50",
    "SMA_150": "SMA150",
    "SMA_200": "SMA200",
    "SuperTrend_Up": "SUPERTREND",
    "PRIOR_BREAKOUT_LEVEL": "PRIOR_BREAKOUT_LEVEL",
}


def _price(value) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) and result > 0 else None


def _label(item) -> str:
    anchor = _ANCHORS.get(item.anchor_type)
    if anchor is None and item.code == "PULLBACK_WATCH":
        ev = _current_evidence(item)
        if ev is not None:
            anchor = _ANCHORS.get(_SUPPORT_EVIDENCE.get(ev.code))
    if item.code == "SUPPORT_BREAK" and anchor:
        return f"{anchor} 이탈"
    if item.code == "PULLBACK_WATCH" and anchor:
        return f"{anchor} 눌림목 지지 관찰"
    if item.code in {"SUPPORT_RECLAIM", "BREAKOUT_RECLAIM"} and anchor:
        return f"{anchor} 회복"
    return _OBSERVATION_LABELS[item.code]


def _finality(value) -> str:
    return "잠정" if value is SignalFinality.PROVISIONAL else "확정"


def _current_evidence(item):
    current = next((ev for ev in item.evidence if ev.code == f"{item.code}_CURRENT"), None)
    if current is not None:
        return current
    # SETUP producer는 매 평가일의 실측으로 evidence 자체를 교체한다.
    if item.code == "PULLBACK_WATCH":
        return next((ev for ev in item.evidence if ev.code in _SUPPORT_EVIDENCE), None)
    # 공통 detector는 최초 발생일에 원본 실측만 만들고 이후 _CURRENT를 덧붙인다.
    if item.started_on == item.status_as_of:
        return next((ev for ev in item.evidence if ev.code == item.code), None)
    return None


def _measurement(item, *, provisional=False) -> str:
    ev = _current_evidence(item)
    if ev is None:
        return "현재 실측 없음 — 상세 근거 참조"
    observed, reference = _price(ev.observed_value), _price(ev.reference_value)
    if observed is None or reference is None:
        return "현재 실측/기준값 미평가"
    # 두 값이 가격인 detector에만 가격 단위·이격을 붙인다.
    if item.code in {
        "SUPPORT_BREAK",
        "BREAKOUT_LEVEL_BREACH",
        "PULLBACK_LOW_BREACH",
        "MOMENTUM_DECELERATION",
        "PULLBACK_WATCH",
    }:
        return f"{'현재가격' if provisional else '종가'} {observed:.2f} / 기준 {reference:.2f} ({(observed / reference - 1) * 100:+.2f}%)"
    return f"관측값 {ev.observed_value:g} / 기준값 {ev.reference_value:g}"


def render_analysis_overview(
    scorecard: TechnicalScorecard | None,
    analysis: AnalysisStrategyResult | None,
    *,
    warning: str | None = None,
    detail: bool = False,
    expanded_observations: bool = False,
) -> str:
    if detail:
        return render_strategy_sections(scorecard, analysis, warning=warning, detail=True)
    if scorecard is None:
        return f"### 현재 상태\n\n- 미평가 — {warning or '기술 분석 결과 없음'}"
    day = scorecard.as_of
    lines = [f"**분석 기준: {day} 일봉** · 시간외 시세 미포함"]
    if analysis is None or analysis.strategy_run.as_of != day:
        lines += [
            "",
            "### 현재 상태",
            "",
            f"- 전략·관찰 미평가 — {warning or '분석 결과 없음 또는 평가일 불일치'}",
        ]
        return "\n".join(lines)
    chart = getattr(analysis, "chart_analysis", None)
    provisional = valid_result(chart, day) and quality_finality(chart) == "PROVISIONAL"
    bundles = [b for b in analysis.strategy_run.signal_bundles if b.as_of == day]
    provisional = provisional or any(
        b.entry_opportunity.finality is SignalFinality.PROVISIONAL for b in bundles
    )
    close = _price(analysis.current_close)
    unit = "₩" if is_korean_ticker(scorecard.ticker) else "$"
    if close is not None:
        lines[0] += (
            f" · {'현재가격' if provisional else '종가'} {unit if expanded_observations else ''}{close:,.2f}"
        )
    # 날짜가 맞는 기록만 현재 상태로 사용한다. 입력 payload는 변경하지 않는다.
    if provisional or any(
        b.entry_opportunity.finality is SignalFinality.PROVISIONAL for b in bundles
    ):
        lines[0] += " · 잠정 일봉"
    active, stale = [], 0
    for bundle in bundles:
        for item in bundle.observation_history:
            if (
                item.status is not ObservationStatus.ACTIVE
                or item.temporal_type is not ObservationTemporalType.EPISODE
            ):
                continue
            if (
                item.status_as_of != day
                or item.started_on > day
                or (item.confirmed_on is not None and item.confirmed_on > day)
                or item.ended_on is not None
            ):
                stale += 1
                continue
            active.append((bundle, item))
    current = [(b, i) for b, i in active if not i.source_terminal]
    past = [(b, i) for b, i in active if i.source_terminal]
    current.sort(
        key=lambda pair: (
            pair[1].anchor_type != "SMA150",
            pair[1].direction.value != "RISK",
            str(pair[1].code),
            str(pair[1].anchor_id),
        )
    )
    if expanded_observations:
        lines += ["", render_observation_story(analysis), "", "**기존 지표 참고**", ""]
    else:
        lines += ["", "### 현재 상태", ""]
    if current and not expanded_observations:
        for bundle, item in current:
            lines.append(
                f"- {_label(item)} — {_measurement(item, provisional=provisional)} · {item.started_on}부터 · {_finality(item.finality)} ({bundle.strategy_id})"
            )
        if sum(i.direction.value == "RISK" for _, i in current) > 1:
            lines.append(
                "- 같은 하락을 여러 기준으로 관찰한 항목이므로 위험 개수를 단순 합산하지 않습니다."
            )
    elif not expanded_observations:
        lines.append("- 표시할 현재 관찰 기록 없음 — 미평가 항목은 아래 참조")
    if scorecard.trend.metrics.get("supertrend_direction") == -1:
        lines.append("- Supertrend 하락 방향")
    dimensions = " · ".join(
        f"{label} {dimension.score if dimension.score is not None else '미평가'}"
        for label, dimension in zip(
            ("추세", "구조", "모멘텀", "수급", "안전도"), scorecard.dimensions(), strict=True
        )
    )
    lines.append(f"- 기존 5축 Scorecard: {dimensions}")
    lines += ["", render_quality_overview(analysis), "", "### 주요 가격대", ""]
    levels, seen = [], set()

    def add_level(kind, value, state, owner, identity):
        value = _price(value)
        if value is None or close is None or identity in seen:
            return
        seen.add(identity)
        # 미국/한국 ticker 모두 지원하므로 통화 기호는 ticker로 정한다.
        rise = (
            (
                f" 상승 필요 {(value / close - 1) * 100:+.2f}% |"
                if value > close
                else " 상승 필요 없음 |"
            )
            if expanded_observations
            else ""
        )
        levels.append(
            f"| {kind} | {unit}{value:,.2f} | {(close / value - 1) * 100:+.2f}% |{rise} {state} · {owner} |"
        )

    for bundle, item in current:
        if item.code not in {
            "SUPPORT_BREAK",
            "BREAKOUT_LEVEL_BREACH",
            "PULLBACK_LOW_BREACH",
            "PULLBACK_WATCH",
        }:
            continue
        ev = _current_evidence(item)
        measurements = [ev] if ev is not None else []
        if item.code == "PULLBACK_WATCH":
            measurements = [ev for ev in item.evidence if ev.code in _SUPPORT_EVIDENCE]
        state = "지지 관찰" if item.code == "PULLBACK_WATCH" else "이탈 · 회복 확인선"
        for measurement in measurements:
            kind = _SUPPORT_EVIDENCE.get(measurement.code, item.anchor_type)
            add_level(
                _ANCHORS.get(kind, "구조 기준"),
                measurement.reference_value,
                f"{state} ({_finality(item.finality)})",
                bundle.strategy_id,
                (bundle.strategy_id, item.anchor_id or kind, kind),
            )
    for bundle in bundles:
        for test in bundle.support_tests or ():
            if test.status_as_of != day or test.ended_on is not None:
                continue
            anchor = test.anchor
            states = {
                "HELD": "지지 유지",
                "SOFT_BREACH": "일시 이탈",
                "RECLAIMED": "회복",
                "FAILED": "지지 실패",
            }
            add_level(
                _ANCHORS.get(anchor.anchor_type, anchor.anchor_type),
                anchor.current_value,
                f"{states[test.status]} · 지지 테스트 {test.finality.value}",
                bundle.strategy_id,
                (bundle.strategy_id, anchor.anchor_id, anchor.anchor_type),
            )
        opportunity = bundle.entry_opportunity
        if (
            opportunity.evaluation_as_of != day
            or opportunity.status
            not in {EntryOpportunityStatus.ALLOW, EntryOpportunityStatus.WATCH}
            or opportunity.anchors is None
        ):
            continue
        anchors = opportunity.anchors
        for name, value in (
            ("돌파 후보 기준", anchors.breakout_level),
            ("진입 당시 지지선", anchors.origin_support),
            ("눌림목 저점", anchors.pullback_low),
        ):
            add_level(
                name,
                value,
                f"진입 후보 앵커 · 허가 별도 ({_finality(opportunity.finality)})",
                bundle.strategy_id,
                (bundle.strategy_id, anchors.source_id, name),
            )
    if levels:
        lines += [
            f"| 가격 기준 | 가격 | {'현재가격' if provisional else '종가'}의 기준선 대비 위치 |"
            + (" 현재가격에서 기준선까지 |" if expanded_observations else "")
            + " 의미 / 전략 |",
            "|---|---:|---:|---:|---|" if expanded_observations else "|---|---:|---:|---|",
            *levels,
            "",
            "- 이동평균은 오늘 기준값이며 매일 변합니다. 회복 확인선과 실제 매매 조건은 구분합니다.",
        ]
    else:
        lines.append(
            "- 현재 실측이 있는 유효 가격 기준 없음 — 과거 앵커를 현재 지지선으로 대체하지 않습니다."
        )
    lines += _five_day_lines(analysis, bundles, day, expanded_observations=expanded_observations)
    lines += ["", "### 전략별 대응", "", "| 전략 | 신규 진입 | 보유 대응 |", "|---|---|---|"]
    for verdict in analysis.strategy_run.verdicts:
        if verdict.as_of != day:
            lines.append(f"| {verdict.strategy_id} | 미평가 — 평가일 불일치 | 미평가 |")
            continue
        lines.append(
            f"| {verdict.strategy_id} | {_ENTRY[verdict.entry.intent.value]} ({verdict.entry.data_status.value}) | {_EXIT[verdict.exit.intent.value]} ({verdict.exit.data_status.value}) |"
        )
    if not analysis.strategy_run.verdicts:
        lines.append("| — | 전략 판정 미평가 | 전략 판정 미평가 |")
    for bundle in bundles:
        opportunity = bundle.entry_opportunity
        status = {
            "allow": "진입 가능",
            "watch": "대기",
            "block": "진입 제한",
            "invalidated": "진입 기회 취소",
            "expired": "기회 만료",
            "no_recent_signal": "최근 진입 신호 없음",
            "not_evaluated": "미평가",
        }
        entry = (
            status[opportunity.status.value] if opportunity.evaluation_as_of == day else "미평가"
        )
        today = [s for s in bundle.signal_history if s.occurred_on == day]
        exit_signals = [s for s in today if s.code in {"SMA150_EXIT", "OVERHEAT_CORRECTION"}]
        response = "; ".join(f"{_SIGNALS[s.code]} ({_finality(s.finality)})" for s in exit_signals)
        if expanded_observations and not response:
            plan = analysis.position_plans.get(bundle.strategy_id)
            if plan is not None and plan.directive.kind.value == "keep_current":
                response = "오늘 신규 매매 지시 없음 · 보유 수량 유지"
        lines.append(
            f"| {bundle.strategy_id} | {entry} | {response or '당일 축소·청산 신호 기록 없음'} |"
        )
    lines.append("")
    for verdict in analysis.strategy_run.verdicts:
        if verdict.as_of != day:
            continue
        seen_reasons = set()
        for reason in (*verdict.entry.reasons, *verdict.exit.reasons):
            if reason.importance.value == "high":
                key = (reason.code, reason.message, reason.observed_value, reason.reference_value)
                if key not in seen_reasons:
                    seen_reasons.add(key)
                    lines += _decision_evidence_lines([reason], first_label=verdict.strategy_id)
    for bundle in bundles:
        lines += _entry_review_lines(bundle, day, current_close=close)
    lines += _position_plan_lines(analysis, expanded_observations=expanded_observations)
    lines.append("- 관찰 위험 자체는 축소·청산 명령이 아닙니다. 위 전략의 보유 대응을 확인합니다.")
    if past:
        prices = sorted(
            {
                _price(ev.reference_value)
                for _, item in past
                if (ev := _current_evidence(item)) is not None
                and _price(ev.reference_value) is not None
            }
        )
        price_text = (
            ", ".join(f"${value:,.2f}" for value in prices)
            if not is_korean_ticker(scorecard.ticker)
            else ", ".join(f"₩{value:,.2f}" for value in prices)
        )
        lines += [
            "",
            "### 과거 구조 — 참고",
            "",
            f"- 진입 기회 종료 후에도 미회복인 기준 {len(past)}개"
            + (f": {price_text}" if prices else ""),
            "- 과거 돌파·지지 구조의 참고값이며 현재 진입 허가나 신규 매매선이 아닙니다.",
        ]
    lines += ["", "### 평가 범위 / 상세", ""]
    if stale or len(bundles) != len(analysis.strategy_run.signal_bundles):
        lines.append("- 평가일 불일치 기록은 현재 상태에서 제외했습니다.")
    if not bundles:
        lines.append("- 관찰 미평가 — Strategy bundle 없음")
    for bundle in bundles:
        missing = [
            line
            for line in _observation_evaluation_lines(bundle, False)
            if "미평가" in line or "미구현" in line
        ]
        if missing:
            lines.append(
                f"- {bundle.strategy_id}: 관찰 일부 미평가 ({len(missing)}항목). "
                + (
                    "Observation 비활성."
                    if bundle.observations_enabled is False
                    else "거래량 등 미선정 규칙·입력 상태는 상세 참조."
                )
            )
    for message in (
        warning,
        analysis.warning,
        analysis.score_history_warning,
        *analysis.strategy_run.errors,
        *analysis.strategy_run.diagnostic_errors,
    ):
        if message:
            lines.append(f"- {message}")
    lines.append(
        "- Technical Score·5축 Scorecard는 기존 지표, Quality는 새 4축 상태 지수입니다. 점수만으로 매매하지 않습니다."
    )
    lines.append("- 전체 Observation·Signal 이력, Legacy·A′ 및 계산 근거: --detail-strategy")
    return "\n".join(lines)


def _entry_review_lines(bundle, day, *, current_close=None):
    opportunity = bundle.entry_opportunity
    if opportunity.evaluation_as_of != day:
        return [f"- {bundle.strategy_id} 진입 기회 미평가 — 평가일 불일치"]
    lines = [
        f"- {bundle.strategy_id} 진입 기회: {_opportunity_reason(opportunity)} · {_finality(opportunity.finality)}"
    ]
    terminal = opportunity.status in {
        EntryOpportunityStatus.INVALIDATED,
        EntryOpportunityStatus.EXPIRED,
    }
    if terminal:
        lines[0] += f" · 종료일 {opportunity.terminal_on or '미확인'}"
        label = (
            "종료 당시 가격 근거"
            if opportunity.evidence and opportunity.evidence[0].code == "BREAKOUT_ATR_INVALIDATED"
            else "현재 평가 참고"
        )
        lines += _decision_evidence_lines(opportunity.evidence[:1], first_label=label)
    else:
        lines += _decision_evidence_lines(opportunity.evidence)
    if opportunity.status in {EntryOpportunityStatus.ALLOW, EntryOpportunityStatus.WATCH}:
        signal = opportunity.entry_signal
        if signal is not None:
            age = f" · {opportunity.age_bars}거래일 전" if opportunity.age_bars is not None else ""
            lines.append(
                f"  - 진입 신호: {_SIGNALS.get(signal.code, signal.code)} · 발생일 {signal.occurred_on}{age} · {_finality(signal.finality)}"
            )
            lines += _decision_evidence_lines(signal.evidence, first_label="발생 원인")
        if opportunity.execution_reference_price is not None:
            basis = "Signal 종가 추정" if opportunity.age_bars == 0 else "다음 실제 거래 가능 시가"
            lines.append(
                f"  - {basis} {opportunity.execution_reference_price:g} · 현재 진입 허가와 구분되는 신호 기준가격"
            )
    shadow = getattr(bundle, "entry_shadow", None)
    if shadow is None or shadow.evaluation_as_of != day:
        lines.append(f"- {bundle.strategy_id} 보조 위험: 미평가")
    elif shadow.risk_level is None:
        lines.append(f"- {bundle.strategy_id} 보조 위험: 미평가 — {shadow.reason}")
    else:
        labels = {"NORMAL": "정상", "CAUTION": "주의", "HIGH_RISK": "높음"}
        level = labels.get(shadow.risk_level.value.upper(), shadow.risk_level.value)
        context = " · 종료된 진입 구조의 참고 진단" if terminal else " · 진입 구조의 참고 진단"
        lines.append(
            f"- {bundle.strategy_id} 보조 위험: {level} ({_finality(shadow.finality)}){context} · 현재 평가일 {day}"
        )
        anchors = shadow.anchors
        if anchors is not None:
            if anchors.source_date <= day:
                source = _SIGNALS.get(anchors.source_type, anchors.source_type)
                lines.append(f"  - 출처: {source} · 진입 신호일 {anchors.source_date}")
            else:
                lines.append("  - 출처 미평가 — 진입 신호일이 현재 평가일 이후")
        else:
            lines.append("  - 출처·진입 신호일 미평가")
        for flag in shadow.risk_flags:
            occurred = getattr(flag, "occurred_on", None)
            confirmed = getattr(flag, "confirmed_on", None)
            if (occurred is not None and occurred > day) or (
                confirmed is not None
                and (confirmed > day or (occurred is not None and confirmed < occurred))
            ):
                lines.append("  - 보조 위험 항목 미평가 — 발생일·확정일 불일치")
                continue
            dates = f"발생일 {occurred}" if occurred is not None else "발생일 미확인"
            dates += f" · 첫 확정일 {confirmed}" if confirmed is not None else " · 첫 확정일 미확인"
            lines.append(f"  - {flag.message} ({_finality(flag.finality)}) · {dates}")
            for evidence in flag.evidence[:2]:
                observed, reference = (
                    _price(evidence.observed_value),
                    _price(evidence.reference_value),
                )
                if observed is not None and reference is not None:
                    price_label = (
                        f"발생 당시 가격({occurred or '발생일 미확인'})"
                        if flag.code == "EARLY_FAILED_BREAKOUT_CANDIDATE"
                        else "평가가격"
                    )
                    lines.append(
                        f"    - {price_label} {observed:,.2f} / 기준 {reference:,.2f} ({(observed / reference - 1) * 100:+.2f}%)"
                    )
                else:
                    lines.append(f"    - {evidence.message} · 실측 또는 기준값 미평가")
        if current_close is not None:
            lines.append(f"  - 현재가격 {current_close:,.2f} · 평가일 {day}")
        lines.append(
            "  - 보조 위험은 신규 매도 명령이 아니며 전략 판단·수량 계획을 변경하지 않습니다."
        )
    return lines


def _five_day_lines(analysis, bundles, day, *, expanded_observations=False):
    sessions = sorted({d for d in analysis.exchange_sessions if d <= day})
    history = {p.date: p for p in analysis.score_history if p.date <= str(day)}
    quality = quality_history_by_day(analysis, day)
    days = sessions[-5:]
    changes = {d: [] for d in days}
    short = {d: [] for d in days}
    short_labels = {
        "HIGHER_HIGH": "고점 상승",
        "HIGHER_LOW": "저점 상승",
        "LOWER_HIGH": "고점 하락",
        "LOWER_LOW": "저점 하락",
        "MOMENTUM_DECELERATION": "모멘텀 약화",
        "MOMENTUM_REACCELERATION": "모멘텀 회복",
    }
    for bundle in bundles:
        for item in bundle.observation_history:
            if item.status_as_of > day or (
                item.confirmed_on is not None and item.confirmed_on > day
            ):
                continue
            label = _label(item)
            concise = short_labels.get(item.code, label)
            if item.temporal_type is ObservationTemporalType.EVENT:
                event_day = item.confirmed_on or item.started_on
                if event_day in changes:
                    confirmed = label if label.endswith("확인") else f"{label} 확인"
                    changes[event_day].append(f"{confirmed} ({_finality(item.finality)})")
                    short[event_day].append(concise)
            else:
                if item.started_on in changes:
                    changes[item.started_on].append(f"{label} 시작 ({_finality(item.finality)})")
                    short[item.started_on].append(concise)
                if item.ended_on in changes:
                    status = {
                        "resolved": "관찰 종료",
                        "resolved_to_signal": "전략 신호로 전환",
                        "invalidated": "전제 무효",
                        "expired": "기간 만료",
                    }.get(item.status.value, "종료")
                    changes[item.ended_on].append(f"{label} {status}")
                    short[item.ended_on].append(f"{concise} 종료")
        for signal in bundle.signal_history:
            if signal.occurred_on in changes:
                label = _SIGNALS.get(signal.code, signal.code)
                changes[signal.occurred_on].append(
                    f"{bundle.strategy_id}: {label} ({_finality(signal.finality)})"
                )
                # 긴 신호 설명은 아래 핵심 변화에서 읽고 표에서는 발생 여부를 먼저 본다.
                kind = {"SMA150_EXIT": "청산", "OVERHEAT_CORRECTION": "축소"}.get(
                    signal.code, "진입" if signal.code.endswith("_ENTRY") else "신호"
                )
                short[signal.occurred_on].insert(
                    0, f"{bundle.strategy_id.replace('_W150', '')} {kind}"
                )
    lines = [
        "",
        "### 최근 5거래일",
        "",
        "| 거래일 | 종가/현재가격(등락) | Quality(전일차) | 기술점수(Δ) | 주요 관찰 변화 |",
        "|---|---:|---:|---:|---|",
    ]
    for d in days:
        point = history.get(str(d))
        idx = sessions.index(d)
        previous = history.get(str(sessions[idx - 1])) if idx else None
        price_text = score_text = "미평가"
        if point:
            price = _price(point.close)
            prev_price = _price(previous.close) if previous else None
            price_text = f"{price:,.2f}" if price else "미평가"
            price_text += (
                f" ({(price / prev_price - 1) * 100:+.2f}%)" if price and prev_price else " (—)"
            )
            score_text = str(point.adjusted_score)
            score_text += (
                f" ({point.adjusted_score - previous.adjusted_score:+d})" if previous else " (—)"
            )
        quality_result = quality.get(d)
        prior_quality = quality.get(sessions[idx - 1]) if idx else None
        if point is None:
            price = _price(quality_close(quality_result))
            prior_price = (
                _price(previous.close)
                if previous is not None
                else _price(quality_close(prior_quality))
            )
            if price is not None:
                price_text = f"{price:,.2f}"
                price_text += (
                    f" ({(price / prior_price - 1) * 100:+.2f}%)" if prior_price else " (—)"
                )
        if quality_result is not None and quality_finality(quality_result) == "PROVISIONAL":
            price_text = f"잠정 현재가격 {price_text}"
            if point:
                score_text = f"잠정 {score_text}"
        quality_text = quality_cell(quality_result, prior_quality, current_day=day)
        facts = list(dict.fromkeys(short[d]))
        summary = (
            facts[0] + (f" 외 {len(facts) - 1}건" if len(facts) > 1 else "")
            if facts
            else "관찰·신호 전환 없음"
        )
        lines.append(f"| {d} | {price_text} | {quality_text} | {score_text} | {summary} |")
    if not days:
        lines.append("| — | 미평가 | 미평가 | 미평가 | 거래소 세션 정보 없음 |")
    lines += [
        "",
        "- 기술점수는 기존 Technical Score입니다. Δ·전일차는 직전 거래일 대비이며, —는 비교 데이터 없음입니다. Quality는 각 날짜 원점에서 계산한 결과이며 빈 날짜를 보간하지 않습니다.",
        "",
        "**핵심 변화**",
    ]
    lines += quality_change_lines(analysis, days, day)
    important = [(d, text) for d in days for text in dict.fromkeys(changes[d])]
    if expanded_observations:
        lines.append("- 관찰·전략 신호의 날짜별 근거는 위 관찰 흐름을 참조합니다.")
    elif important:
        lines.extend(f"- {d}: {text}" for d, text in important)
    else:
        lines.append(
            "- 관찰·전략 신호의 새 전환 기록 없음. 점수 변화는 위 Quality와 아래 Technical Score를 참조합니다."
        )
    points = [history[str(d)] for d in days if str(d) in history]
    if len(points) >= 2:
        first, last = points[0], points[-1]
        lines.append(
            f"- Technical Score: {first.date} {first.adjusted_score} → {last.date} {last.adjusted_score} ({last.adjusted_score - first.adjusted_score:+d}점)"
        )
        if last.change_drivers:
            lines.append(f"- 최근 점수 변화 근거: {'; '.join(last.change_drivers[:2])}")
    lines.append(
        "- 신호는 해당 날짜의 발생 기록입니다. 과거 각 날짜의 전략 판단을 현재 판정으로 추정하지 않습니다."
    )
    return lines


def _position_plan_lines(analysis, *, expanded_observations=False):
    plans = analysis.position_plans
    if not plans and analysis.position_plan is not None:
        plans = {"호환 Position Plan": analysis.position_plan}
    lines = [
        "",
        "**전략별 수량**",
        "",
        "- 같은 보유·계좌 입력의 독립 대안이며 수량을 합산하지 않습니다.",
    ]
    if not plans:
        return [*lines, "- 수량 미산정 — 보유 입력 또는 전략 평가를 확인할 수 없습니다."]
    lines += [
        "",
        "| 전략 | 계획 | 보유(주) | 목표(주) | 매수(주) | 매도(주) | 산정 상태 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    labels = {
        "build_only_to_risk_target": "위험 예산 내 진입",
        "keep_current": "유지",
        "reduce_current_by_fraction": "일부 축소",
        "flat": "청산",
        "freeze": "판단 보류",
    }
    notes = []
    for strategy_id, plan in plans.items():
        quantities = [
            str(value) if value is not None else "미산정"
            for value in (
                plan.current_quantity,
                plan.target_quantity,
                plan.buy_quantity,
                plan.sell_quantity,
            )
        ]
        state = "산정 완료" if plan.quantity_status.value == "available" else "수량 미산정"
        lines.append(
            f"| {strategy_id} | {labels[plan.directive.kind.value]} | {' | '.join(quantities)} | {state} |"
        )
        if plan.signal_finality is not None:
            notes.append(f"- {strategy_id}: 신호 {_finality(plan.signal_finality)}")
        if plan.quantity_status.value == "unavailable":
            notes.append(
                f"- {strategy_id}: 수량 미산정 — 자본·위험 예산·주당 위험·시세 또는 다음 세션 실행 확인 부족"
            )
        if plan.directive.kind.value == "freeze":
            notes.append(f"- {strategy_id}: 미평가로 수량 변경을 보류합니다")
        if expanded_observations and plan.directive.kind.value == "keep_current":
            notes.append(
                f"- {strategy_id}: 오늘 신규 매매 지시 없음 · 보유 수량 유지. 과거 청산 신호를 오늘 매도 수량에 반영하지 않습니다."
            )
    return [*lines, "", *notes] if notes else lines
