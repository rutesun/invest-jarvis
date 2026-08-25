"""brief 마크다운 렌더러 — 순수 함수.

LLM narrative가 없으면(실패/미사용) 규칙 원문으로 슬롯을 채운다 (스펙 §6.1 fallback).
데이터 없는 슬롯은 항목 자체를 생략한다 (스펙 §6.2).
"""

from __future__ import annotations

from datetime import datetime

from src.tools.brief.models import BUCKET_LABELS, BriefItem
from src.tools.macro import TickerMacroSnapshot


def render_markdown(
    date: datetime,
    macro: TickerMacroSnapshot | None,
    items: list[BriefItem],
    top_n: int = 3,
) -> str:
    lines: list[str] = [f"# Daily Brief — {date.strftime('%Y-%m-%d')}", ""]

    lines.extend(_macro_section(macro))

    if not items:
        lines.append("설정된 종목 없음 — playbook.yaml에 holdings/watchlist를 추가하세요.")
        return "\n".join(lines)

    lines.extend(_top_actions_section(items, top_n))

    holdings = [i for i in items if i.kind == "holding"]
    watches = [i for i in items if i.kind == "watch"]
    if holdings:
        lines.append(f"## 보유 ({len(holdings)}종목)")
        lines.append("")
        for item in holdings:
            lines.extend(_item_section(item))
    if watches:
        lines.append(f"## 워치리스트 ({len(watches)}종목)")
        lines.append("")
        for item in watches:
            lines.extend(_item_section(item))

    return "\n".join(lines)


def _macro_section(macro: TickerMacroSnapshot | None) -> list[str]:
    if macro is None:
        return []
    return [
        "## 시장 환경",
        f"VIX {macro.vix:.1f} ({macro.vix_change:+.1f}) · "
        f"Fear&Greed {macro.fear_greed} ({macro.fear_greed_label}) · "
        f"10Y {macro.us_10y:.2f}% · DXY {macro.dxy:.1f}",
        "",
    ]


def _top_actions_section(items: list[BriefItem], top_n: int) -> list[str]:
    lines = [f"## ⚡ 오늘의 액션 (Top {top_n})", ""]
    for rank_no, item in enumerate(items[:top_n], start=1):
        label = BUCKET_LABELS.get(item.bucket, "?")
        marker = f" ⚠{' ·'.join(item.markers)}" if item.markers else ""
        remaining = f" — 남은 조건: {item.remaining_condition}" if item.remaining_condition else ""
        lines.append(f"{rank_no}. [{label}] {item.ticker}{marker}{remaining}")
    lines.append("")
    return lines


def _item_section(item: BriefItem) -> list[str]:
    label = BUCKET_LABELS.get(item.bucket, "?")
    lines: list[str] = []

    if item.action == "error":
        lines.append(f"### {item.ticker} — 데이터 조회 실패")
        lines.append(f"- **오류**: {item.error}")
        lines.append("")
        return lines

    title_extra = ""
    exit_v = item.verdict.exit_verdict if item.verdict else None
    if exit_v is not None and exit_v.current_r is not None:
        title_extra = f" (R={exit_v.current_r:.2f})"
    gate = item.verdict.gate if item.verdict else None
    if gate is not None and gate.quality_grade:
        title_extra = f" (grade {gate.quality_grade})"
    lines.append(f"### {item.ticker} — {label}{title_extra}")

    if item.note:
        lines.append(f"- **메모**: {item.note}")

    # 판정 근거 — 규칙 원문 (LLM과 무관하게 항상 표기)
    if exit_v is not None:
        sig_text = " / ".join(f"{s.code}({s.severity}): {s.detail}" for s in exit_v.signals)
        lines.append(f"- **판정 근거**: {exit_v.detail}" + (f" — {sig_text}" if sig_text else ""))
    elif gate is not None:
        req = [c for c in gate.checklist if c.required]
        check_text = " · ".join(
            f"{c.name}{'✅' if c.met else '❌' if c.met is False else '—'}" for c in req
        )
        reason = gate.veto_reason or "전 조건 충족"
        lines.append(f"- **판정 근거**: {check_text} — {reason}")
    if item.remaining_condition:
        lines.append(f"- **남은 조건**: {item.remaining_condition}")

    # 가격/기술 — narrative 있으면 문장, 없으면 수치 원문
    price_part = f"현재가 {item.price:,.2f}" if item.price is not None else ""
    change_part = f" ({item.change_pct:+.1f}%)" if item.change_pct is not None else ""
    narrative = item.narrative
    tech_note = getattr(narrative, "technical_note", None) if narrative else None
    tech_line = f"{price_part}{change_part}"
    if tech_note:
        tech_line = f"{tech_line} · {tech_note}" if tech_line else tech_note
    if tech_line:
        lines.append(f"- **가격/기술**: {tech_line}")

    if item.technical_verdict:
        verdict = item.technical_verdict
        reasons = verdict.get("reasons") or []
        cautions = verdict.get("cautions") or []
        trend = verdict.get("score_trend_summary")
        detail_parts = []
        if reasons:
            detail_parts.append(reasons[0])
        if cautions:
            detail_parts.append(f"주의: {cautions[0]}")
        if trend:
            detail_parts.append(trend)
        verdict_line = f"- **기술 Verdict**: {verdict.get('action')}"
        if detail_parts:
            verdict_line = f"{verdict_line} — {' / '.join(detail_parts)}"
        lines.append(verdict_line)

    if item.turnaround:
        lines.append(f"- **{item.turnaround}**")

    # 사이징 (게이트 통과 시)
    plan = item.verdict.position_plan if item.verdict else None
    if plan is not None and plan.error is None:
        shares_part = f"{plan.shares}주 " if plan.shares is not None else ""
        lines.append(
            f"- **사이징**: {shares_part}@ {plan.entry:.2f}, stop {plan.stop:.2f} ({plan.stop_basis})"
        )

    # 수급 (KR만, 데이터 있을 때만)
    flow_note = getattr(narrative, "flow_note", None) if narrative else None
    if item.flow is not None:
        fallback = f"외국인 5일 {item.flow.foreign_direction_5d} · 기관 5일 {item.flow.institution_direction_5d}"
        lines.append(f"- **수급(KR)**: {flow_note or fallback}")

    # 뉴스 (있을 때만)
    if item.news:
        news_note = getattr(narrative, "news_note", None) if narrative else None
        titles = " · ".join(f'"{n.title}"' for n in item.news[:3])
        lines.append(f"- **뉴스**: {titles}" + (f" — {news_note}" if news_note else ""))

    # 공시 (있을 때만)
    if item.disclosures:
        disc = " · ".join(f"{d.form_type} {d.description} ({d.date})" for d in item.disclosures[:3])
        lines.append(f"- **공시**: {disc}")

    # 스탑 상태 (보유 + stop_price 있을 때만)
    if item.holding is not None and item.holding.stop_price and item.price:
        dist_pct = (item.price - item.holding.stop_price) / item.holding.stop_price * 100
        near = " ⚠근접" if "스탑 근접" in item.markers else ""
        lines.append(
            f"- **스탑 상태**: 스탑 {item.holding.stop_price:,.2f} 대비 {dist_pct:+.1f}%{near}"
        )

    # 다음 확인 지점 — narrative 있으면 문장, 없으면 trailing_stop 원문
    next_check = getattr(narrative, "next_check", None) if narrative else None
    if not next_check and exit_v is not None and exit_v.trailing_stop is not None:
        next_check = f"trailing stop(SMA50) {exit_v.trailing_stop:,.2f} 이탈 여부"
    if next_check:
        lines.append(f"- **다음 확인 지점**: {next_check}")

    lines.append("")
    return lines
