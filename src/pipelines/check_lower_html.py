"""기존 check 결과를 읽어 전략·관찰·Quality의 하단 표시만 구성한다."""

from __future__ import annotations

import re
from collections import defaultdict
from html import escape

from src.pipelines.quality_overview import (
    AXES,
    compatible,
    finality,
    number,
    previous_result,
    quality_history_by_day,
    quality_value,
    valid_result,
)
from src.pipelines.strategy_render import _opportunity_reason


LOWER_STYLE = """
.check-lower { margin-top:28px; } .lower-strategies,.lower-columns { display:grid;
  gap:20px; grid-template-columns:repeat(3,minmax(0,1fr)); }
.lower-columns { grid-template-columns:minmax(0,1fr); gap:0; }
.check-lower section { min-width:0; } .strategy-card { background:#f2f6f8; padding:18px;
  border-radius:8px; overflow-wrap:anywhere; } .strategy-card h4 { margin:0 0 10px; }
.strategy-action { font-size:1.2rem; font-weight:600; } .strategy-quantity { font-size:1.15rem; }
.strategy-card details { border-top:1px solid #dfe6ea; margin-bottom:0; }
.strategy-card summary { padding-bottom:0; } .lower-muted { color:#425665; }
.lower-up { color:#176b43; } .lower-down { color:#ac3030; }
.quality-latest,.strategy-quantity,.axis-value,.axis-delta { font-variant-numeric:tabular-nums; }
.quality-score { font-size:2rem; font-weight:600; color:#17252e; }
.observation-timeline { list-style:none; padding:0; } .observation-day { border-bottom:1px solid #dfe6ea;
  padding:10px 0; } .observation-day time { color:#425665; font-variant-numeric:tabular-nums; }
.observation-day details { margin:0; } .observation-day summary { padding:8px 0; }
.check-lower .quality-chart { width:100%; max-width:560px; height:auto; display:block; }
.check-lower .quality-chart text { font-size:18px; }
.check-lower .quality-chart .quality-value { fill:#17252e; font-size:18px; }
.quality-chart .quality-missing { font-size:11px; } .quality-axis { margin:14px 0; }
.axis-heading,.axis-caption { display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; }
.axis-caption { color:#425665; font-size:.85rem; margin-top:4px; }
.axis-track { height:6px; background:#edf1f3; margin-top:6px; }
.axis-track span { display:block; height:100%; background:#52778b; }
.quality-relative { color:#425665; font-size:.9rem; } .lower-details { border-top:1px solid #dfe6ea;
  padding-top:12px; } .quality-warning { background:#fff4e6; color:#425665; padding:12px; }
@media(max-width:800px) { .lower-strategies,.lower-columns { grid-template-columns:minmax(0,1fr); }
  .lower-columns { gap:8px; } }
"""

_ENTRY = {
    "allow": "진입 가능",
    "watch": "대기",
    "block": "진입 제한",
    "not_evaluated": "미평가",
    "invalidated": "진입 기회 취소",
    "expired": "기회 만료",
    "no_recent_signal": "최근 진입 신호 없음",
}
_EXIT = {"hold": "보유", "reduce": "일부 축소", "exit": "청산 판정", "not_evaluated": "판단 미평가"}
_LABELS = {
    "TECHNICAL_LEGACY": "기존 기술 전략",
    "PLAYBOOK_V1": "Playbook",
    "SWING_W150": "150일선 전략",
}


def _change(value, prior, *, prefix):
    if value is None or prior is None:
        return f'<span class="axis-delta lower-muted">{prefix} 미평가</span>'
    delta = value - prior
    direction = "up" if delta > 0 else "down" if delta < 0 else "muted"
    word = "상승" if delta > 0 else "하락" if delta < 0 else "유지"
    return f'<span class="axis-delta lower-{direction}">{prefix} {delta:+.2f}점 · {word}</span>'


def _strategy_cards(analysis, markdown):
    day, run = analysis.scorecard.as_of, analysis.strategy_run
    verdicts = {v.strategy_id: v for v in run.verdicts}
    bundles = {b.strategy_id: b for b in run.signal_bundles}
    plans = analysis.position_plans or (
        {"호환 Position Plan": analysis.position_plan} if analysis.position_plan is not None else {}
    )
    owners = dict.fromkeys([*verdicts, *plans, *bundles])
    cards = []
    for owner in owners:
        verdict, bundle, plan = verdicts.get(owner), bundles.get(owner), plans.get(owner)
        entry, action, reasons = "미평가", "판단 미평가", []
        if verdict is not None and verdict.as_of == day and run.as_of == day:
            entry = _ENTRY[verdict.entry.intent.value]
            action = _EXIT[verdict.exit.intent.value]
            reasons += [r.message for r in (*verdict.entry.reasons, *verdict.exit.reasons)]
        elif verdict is not None:
            reasons.append("평가일 불일치 · 전략 판단 미평가")
        if bundle is not None and bundle.as_of == day and run.as_of == day:
            opportunity = bundle.entry_opportunity
            if opportunity.evaluation_as_of == day:
                entry = _ENTRY[opportunity.status.value]
                reasons.append(_opportunity_reason(opportunity))
            else:
                entry = "미평가 — 평가일 불일치"
            if verdict is None:
                exits = [
                    s
                    for s in bundle.signal_history
                    if s.occurred_on == day and s.code in {"SMA150_EXIT", "OVERHEAT_CORRECTION"}
                ]
                if exits:
                    action = " · ".join(
                        "150일선 청산 조건 충족" if s.code == "SMA150_EXIT" else "과열 후 조정"
                        for s in exits
                    )
                elif (
                    bundle.data_status.value == "complete"
                    and opportunity.evaluation_as_of == day
                    and opportunity.status.value != "not_evaluated"
                ):
                    action = (
                        "오늘 신규 매매 지시 없음"
                        if plan is not None and plan.directive.kind.value == "keep_current"
                        else "당일 축소·청산 신호 기록 없음"
                    )
        elif bundle is not None:
            reasons.append("평가일 불일치 · 진입 기회 미평가")
        provisional = bool(
            bundle is not None
            and bundle.as_of == day
            and bundle.entry_opportunity.finality.value == "provisional"
        ) or bool(plan and plan.signal_finality and plan.signal_finality.value == "provisional")
        state = '<p class="warning">장중 잠정 결과 · 마감 전 변동 가능</p>' if provisional else ""
        if plan is None:
            quantities = '<p class="strategy-quantity">수량 미산정</p><p>보유 입력 또는 전략 평가를 확인할 수 없습니다.</p>'
        else:
            target = f"{plan.target_quantity:,}" if plan.target_quantity is not None else "미산정"
            buy = f"{plan.buy_quantity:,}" if plan.buy_quantity is not None else "미산정"
            sell = f"{plan.sell_quantity:,}" if plan.sell_quantity is not None else "미산정"
            status = "산정 완료" if plan.quantity_status.value == "available" else "수량 미산정"
            quantities = (
                f'<p class="strategy-quantity">{plan.current_quantity:,} → {target} 주</p>'
                f'<p class="lower-muted">보유 → 목표 · 매수 {buy} · 매도 {sell}</p><p>{status}</p>'
            )
        if plan is not None:
            labels = {
                "build_only_to_risk_target": "위험 예산 내 진입",
                "keep_current": "유지",
                "reduce_current_by_fraction": "일부 축소",
                "flat": "청산",
                "freeze": "판단 보류",
            }
            quantities += f"<p>수량 계획: {labels[plan.directive.kind.value]}</p>"
        evidence = (
            markdown("\n".join(f"- {reason}" for reason in reasons))
            if reasons
            else "<p>전략 판정 근거 미평가 · 전체 상세 참조</p>"
        )
        cards.append(
            f'<section class="strategy-card" data-strategy="{escape(owner)}"><h4>{escape(_LABELS.get(owner, owner))}</h4>'
            f'<p class="lower-muted">{escape(owner)}</p><p class="strategy-action">{escape(action)}</p>'
            f"<p>신규 진입: {escape(entry)}</p>{state}{quantities}"
            f"<details><summary>판단 근거</summary>{evidence}</details></section>"
        )
    return (
        '<section class="section"><h3>전략별 대응 · 전략별 수량</h3>'
        '<p class="lower-muted">같은 보유·계좌 입력의 독립 대안이며 수량을 합산하지 않습니다.</p>'
        '<div class="lower-strategies">'
        + ("".join(cards) or "<p>전략 판단·수량 미평가 — 평가 결과 없음</p>")
        + "</div></section>"
    )


def _observation(analysis, text, markdown):
    groups = defaultdict(list)
    context = ""
    for line in text.splitlines():
        if line.startswith("#### "):
            context = line[5:]
        match = re.match(r"^- (\d{4}-\d{2}-\d{2}): (.*)$", line)
        if match:
            groups[match[1]].append((context, match[2]))
    timeline = []
    for day, entries in sorted(groups.items()):
        items = "".join(
            f"<li>{escape(context)} · {escape(event)}</li>" for context, event in entries
        )
        # 날짜만 접혀 있어도 사건의 종류와 출처를 읽을 수 있게 첫 줄을 남긴다.
        summary = " · ".join(dict.fromkeys(event.split(" · ")[0] for _, event in entries))
        if any("잠정" in event for _, event in entries):
            summary += " · 잠정 포함"
        timeline.append(
            f'<li class="observation-day" data-day="{day}"><time datetime="{day}">{day}</time>'
            f"<details><summary>{escape(summary)}</summary><ul>{items}</ul></details></li>"
        )
    heading = "최근 20개 반환 거래일의 관찰·신호와 현재 상태의 근원 사건입니다."
    if not groups:
        timeline.append("<li>기간 내 관찰·신호 기록 없음 — 미평가 항목은 현재 상태 참조</li>")
    return (
        '<details class="lower-observation-all"><summary>지난 관찰 전체 보기</summary>'
        '<section class="section lower-observation"><h3>관찰 흐름</h3>'
        f'<p class="lower-muted">{heading}</p><ol class="observation-timeline">'
        + "".join(timeline)
        + "</ol>"
        f"<details><summary>기준별 관찰 원문 · 기존 지표 참고</summary>{markdown(text)}</details></section></details>"
    )


def _quality_chart(analysis):
    day = analysis.scorecard.as_of
    days = sorted({d for d in analysis.exchange_sessions if d <= day})[-5:]
    if not days:
        return ""
    history = quality_history_by_day(analysis, day)
    marks, previous = [], None
    for index, current_day in enumerate(days):
        point = history.get(current_day)
        value = quality_value(point, current_day=day)
        x = 60 + index * 239 / max(1, len(days) - 1)
        marks.append(f'<text x="{x:g}" y="148" text-anchor="middle">{current_day:%m/%d}</text>')
        if value is None:
            state = "미산출" if point else "미평가"
            marks.append(
                f'<text class="quality-missing" x="{x:g}" y="115" text-anchor="middle">{state}</text>'
            )
            previous = None
            continue
        y = 100 - max(0, min(100, value)) * 0.8
        provisional = finality(point) == "PROVISIONAL"
        state = "장중 잠정" if provisional else "확정"
        if previous is not None and compatible(previous[2], point):
            dash = ' stroke-dasharray="4 3"' if provisional else ""
            marks.append(f'<polyline points="{previous[0]:g},{previous[1]:g} {x:g},{y:g}"{dash}/>')
        shape = " provisional" if provisional else ""
        marks.append(
            f'<circle class="quality-point{shape}" cx="{x:g}" cy="{y:g}" r="4">'
            f"<title>{current_day} {state} {value:.2f}/100</title></circle>"
        )
        # 18px 글자 높이와 점 반지름·하강부 여유를 확보한다. 높은 점수는 아래에 쓴다.
        label_y = y + 24 if index % 2 or y < 32 else y - 10
        marks.append(
            f'<text class="quality-value" x="{x:g}" y="{label_y:g}" text-anchor="middle">{value:.2f}</text>'
        )
        previous = x, y, point
    return (
        '<svg class="quality-chart" viewBox="0 0 332 166" role="img" aria-label="Quality 추이">'
        "<title>최근 5거래일 Quality 추이 · 0~100</title>"
        "<desc>결측과 비교 불가 구간을 연결하지 않습니다. 빈 원과 점선은 장중 잠정값입니다. 날짜별 원표에서 수치를 확인합니다.</desc>"
        '<path d="M42 20H324 M42 60H324 M42 100H324" fill="none" stroke="#dce4e9"/>'
        '<text x="0" y="24">100</text><text x="8" y="64">50</text><text x="16" y="104">0</text>'
        + "".join(marks)
        + "</svg>"
    )


def _axes(analysis, current, history):
    day = analysis.scorecard.as_of
    valid = valid_result(current, day)
    previous = previous_result(analysis, day, history) if valid else None
    scores = {key: number(current.quality.axes.get(key)) if valid else None for key in AXES}
    provisional = valid and finality(current) == "PROVISIONAL"
    rows = []
    for key, (label, description, _) in AXES.items():
        value = scores[key]
        prior = number(previous.quality.axes.get(key)) if compatible(previous, current) else None
        score = (
            f'<span class="axis-value">{value:.2f}</span>'
            if value is not None
            else "<span>미평가</span>"
        )
        bar = (
            f'<div class="axis-track" role="img" aria-label="{escape(label)} {value:.2f}점"><span style="width:{max(0, min(100, value)):.2f}%"></span></div>'
            if value is not None
            else ""
        )
        rows.append(
            f'<div class="quality-axis"><div class="axis-heading"><span>{escape(label)}</span>{score}</div>{bar}'
            f'<div class="axis-caption"><span>{escape(description)}</span>{_change(value, prior, prefix="전일차")}</div></div>'
        )
    present = {key: value for key, value in scores.items() if value is not None}
    if not valid:
        relative = "평가일 불일치 또는 계산 입력 이용 불가 · 4축 상대 비교 미평가"
    elif not present:
        relative = "4축 모두 미평가 · 상대 비교 미평가"
    elif len(present) < len(AXES):
        relative = "일부 축 미평가 · 전체 4축의 최저 축을 단정할 수 없습니다."
    else:
        smallest = min(present.values())
        labels = [
            AXES[key][0].replace("(Participation)", "")
            for key, value in present.items()
            if value == smallest
        ]
        if len(labels) == 4:
            relative = "4축 점수가 모두 같습니다."
        else:
            relative = "·".join(labels) + (
                "가 공동 최저" if len(labels) > 1 else "가 상대적으로 가장 낮습니다."
            )
    state = " · 장중 잠정" if provisional else ""
    mismatch = " · 평가일 불일치" if current is not None and not valid else ""
    return (
        f'<div class="quality-axes"><h4>평가일 4축 · {day}{state}{mismatch}</h4>'
        + "".join(rows)
        + f'<p class="quality-relative">{escape(relative)} 같은 평가일 점수의 상대 비교이며 등급·매매 권고·수익률 예측이 아닙니다.</p></div>'
    )


def _quality(analysis, text, history_text, markdown):
    day = analysis.scorecard.as_of
    history = quality_history_by_day(analysis, day)
    finals = [
        point
        for _, point in sorted(history.items())
        if finality(point) == "FINAL" and quality_value(point) is not None
    ]
    if finals:
        latest = finals[-1]
        prior = previous_result(analysis, latest.quality.as_of, history)
        previous = quality_value(prior) if compatible(prior, latest) else None
        value = quality_value(latest)
        latest_html = f'<p class="lower-muted">최근 확정 · {latest.quality.as_of}</p><p><span class="quality-score">{value:.2f}</span> / 100</p>{_change(value, previous, prefix="전 거래일 대비")}'
    else:
        latest_html = "<p>최근 확정 Quality 미평가 — 과거 확정 결과 없음</p>"
    # 공개 허용 여부와 경고 문구는 기존 Quality formatter가 결정한다.
    warning_lines = [
        line
        for line in text.splitlines()
        if line.startswith("- ")
        and not any(line.startswith("- " + label + " 근거:") for label, _, _ in AXES.values())
    ]
    missing_axes = [
        label
        for label, _, _ in AXES.values()
        if any(
            line.startswith("- " + label + " 근거:")
            and any(word in line for word in ("미평가", "누락", "미산출", "이용 불가"))
            for line in text.splitlines()
        )
    ]
    if missing_axes:
        warning_lines.append("- 실측 근거 미평가: " + "·".join(missing_axes) + " · 상세 근거 참조")
    warning = markdown("\n".join(warning_lines))
    unavailable = getattr(analysis, "quality_history_unavailable", None)
    if unavailable:
        warning += f"<p>Quality 이력 일부 미평가: {escape(str(unavailable))}</p>"
    return (
        '<section class="section lower-quality"><h3>차트 상태 점수(Quality)</h3>'
        '<p class="lower-muted">최근 5개 반환 거래일 · 0~100</p>'
        f'<div class="quality-latest">{latest_html}</div><div class="quality-warning">{warning}</div>'
        + _quality_chart(analysis)
        + _axes(analysis, getattr(analysis, "chart_analysis", None), history)
        + "<details><summary>날짜별 원표 · 기존 기술점수 비교</summary>"
        + markdown(history_text)
        + "</details><details><summary>4축 근거 · 점수 해석</summary>"
        + markdown(text)
        + "</details></section>"
    )


def _visible_warnings(result, sections, markdown):
    lines = [f"- 데이터 주의: {message}" for message in result.get("warnings", ())]
    for title, text in sections:
        if title in {
            "차트 상태 점수(Quality)",
            "평가 범위 / 상세",
            "관찰 흐름",
            "현재 유효 상태",
            "최근 5거래일",
        }:
            continue  # 현재 경고는 현재 패널에, 과거 경고는 접힌 경과에 남긴다.
        lines += [
            line.split(" · 현재 평가일", 1)[0] if " 보조 위험:" in line else line
            for line in text.splitlines()
            if line.startswith("- ")
            and " · 종료된 진입 구조의 참고 진단" not in line
            and any(
                word in line
                for word in (
                    "보조 위험:",
                    "미평가",
                    "미산정",
                    "미산출",
                    "잠정",
                    "경고",
                    "데이터 주의",
                    "반환 거래일 정보 없음",
                )
            )
        ]
    if not lines:
        return ""
    return (
        '<div class="lower-warnings warning">'
        + markdown("\n".join(dict.fromkeys(lines)))
        + "</div>"
    )


def render_lower_sections(result: dict, sections: list[tuple[str, str]], markdown) -> str:
    """차트 아래 section을 재배치한다. 계산과 입력 변경은 수행하지 않는다."""
    analysis = result.get("strategy_analysis")
    if analysis is None or analysis.strategy_run.as_of != analysis.scorecard.as_of:
        chunks = []
        for title, text in sections:
            if title == "관찰 흐름":
                chunks.append(_observation(analysis, text, markdown))
                continue
            kind = "section scope" if title == "평가 범위 / 상세" else "section"
            chunks.append(f'<section class="{kind}">{markdown(text)}</section>')
        return "\n".join(chunks)
    sources = dict(sections)
    chunks = [
        '<div class="check-lower">',
        _strategy_cards(analysis, markdown),
        _visible_warnings(result, sections, markdown),
        '<div class="lower-columns">',
        _quality(
            analysis,
            sources.get("차트 상태 점수(Quality)", ""),
            sources.get("최근 5거래일", ""),
            markdown,
        ),
        "</div>",
        _observation(analysis, sources.get("관찰 흐름", ""), markdown),
    ]
    for title, text in sections:
        if title in {"관찰 흐름", "차트 상태 점수(Quality)", "최근 5거래일"}:
            continue
        if title == "평가 범위 / 상세":
            chunks.append(f'<section class="section scope">{markdown(text)}</section>')
        else:
            chunks.append(
                f'<details class="lower-details"><summary>{escape(title or "추가 근거")}</summary>{markdown(text)}</details>'
            )
    return "\n".join([*chunks, "</div>"])
