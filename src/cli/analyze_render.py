"""Deep dive analysis render functions.

Moved from src/cli/main.py (Task 9). New section formatters (Task 10-15)
and format_deep_dive_output rewrite (Task 16) live here.
"""

from __future__ import annotations

import re

from src.utils.sector_metrics import SectorMetrics


_SEC_DISCLOSURE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+\.(htm|html|txt|xml)$")

METRIC_DISPLAY_NAMES = {
    "pe_ratio": "P/E Ratio",
    "forward_pe": "Forward P/E",
    "peg_ratio": "PEG Ratio",
    "pb_ratio": "P/B Ratio",
    "ps_ratio": "PSR",
    "ev_ebitda": "EV/EBITDA",
    "roe": "ROE",
    "roa": "ROA",
    "revenue_growth": "매출 성장률",
    "earnings_growth": "이익 성장률",
    "gross_margin": "매출총이익률",
    "operating_margin": "영업이익률",
    "profit_margin": "순이익률",
    "debt_to_equity": "Debt/Equity",
    "free_cash_flow": "Free Cash Flow",
    "operating_cash_flow": "Operating Cash Flow",
    "fcf_yield": "FCF Yield",
    "dividend_yield": "배당 수익률",
    "payout_ratio": "배당 성향",
    "current_ratio": "유동비율",
    "quick_ratio": "당좌비율",
    "market_cap": "시가총액",
}


def _get_metric_display_name(metric_name: str) -> str:
    if metric_name not in METRIC_DISPLAY_NAMES:
        return " ".join(word.capitalize() for word in metric_name.split("_"))
    return METRIC_DISPLAY_NAMES[metric_name]


def _format_metric_value(metric_name: str, value: float | None) -> str:
    if value is None:
        return "N/A"
    if metric_name in [
        "revenue_growth",
        "earnings_growth",
        "gross_margin",
        "operating_margin",
        "profit_margin",
        "fcf_yield",
        "dividend_yield",
        "roe",
        "roa",
        "payout_ratio",
    ]:
        return f"{value * 100:.1f}%"
    elif metric_name in ["free_cash_flow", "operating_cash_flow", "market_cap"]:
        return f"${value / 1e9:.1f}B"
    else:
        formatted = f"{value:.2f}" if abs(value) < 10 else f"{value:.1f}"
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def _format_disclosure_title(form_type: str, description: str) -> str:
    text = (description or "").strip()
    if not text:
        return f"{form_type} 공시"
    if _SEC_DISCLOSURE_FILENAME_PATTERN.match(text):
        return f"SEC {form_type} 공시"
    return text


def _format_growth_rate(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:+.2f}%"


def _format_factor_label(value: str) -> str:
    return {
        "technical": "가격",
        "flow": "수급",
        "event": "이벤트",
        "valuation": "밸류에이션",
    }.get(value, value)


def _format_timing_label(value: str) -> str:
    return {
        "조정_대기": "조정 대기",
        "보류": "보류",
        "지금": "지금",
    }.get(value, value)


def _format_factor_section(factor_assessments: list) -> str:
    lines = ["## 팩터 분류", ""]
    for role in ("주도", "보조", "참고"):
        filtered = [item for item in factor_assessments if item.role == role]
        if not filtered:
            continue
        lines.append(f"### {role}")
        lines.append("")
        for item in filtered:
            lines.append(f"- **{_format_factor_label(item.factor_type)}**: {item.summary}")
            lines.append(f"  이유: {item.role_reason}")
        lines.append("")
    return "\n".join(lines)


def _format_scenario_section(scenarios: list) -> str:
    lines = ["## 액션 시나리오", ""]
    for scenario in scenarios:
        lines.append(f"### {scenario.name}")
        lines.append("")
        lines.append(f"- **가격 레벨**: {', '.join(scenario.trigger_price_levels)}")
        lines.append(f"- **확인 조건**: {', '.join(scenario.confirming_factors)}")
        lines.append(f"- **무효화 조건**: {', '.join(scenario.invalidation_conditions)}")
        lines.append(f"- **예상 경로**: {scenario.expected_path}")
        lines.append(f"- **대응**: {scenario.recommended_action}")
        lines.append("")
    return "\n".join(lines)


def _to_payload_dict(item):
    if item is None:
        return None
    return item if isinstance(item, dict) else item.model_dump()


def _format_zone_bounds(zone) -> str:
    zone_dict = _to_payload_dict(zone)
    return f"{zone_dict['lower_bound']:.2f}~{zone_dict['upper_bound']:.2f}"


def _split_supply_zones_by_price(supply_zones, current_price: float) -> tuple[list, list]:
    active_supply = []
    absorbed_supply = []
    for zone in supply_zones:
        zone_dict = _to_payload_dict(zone)
        if zone_dict["upper_bound"] <= current_price:
            absorbed_supply.append(zone)
        else:
            active_supply.append(zone)
    return active_supply, absorbed_supply


def _format_structure_levels(structure_levels, current_price: float) -> str:
    if not structure_levels:
        return ""

    structure_dict = _to_payload_dict(structure_levels)
    demand_zones = structure_dict.get("demand_zones")
    supply_zones = structure_dict.get("supply_zones")
    balance_zones = structure_dict.get("balance_zones")
    if demand_zones is None and supply_zones is None:
        demand_zones = structure_dict.get("support_zones") or []
        supply_zones = structure_dict.get("resistance_zones") or []
        balance_zones = structure_dict.get("former_levels") or []
    demand_zones = demand_zones or []
    supply_zones = supply_zones or []
    balance_zones = balance_zones or []
    active_supply, absorbed_supply = _split_supply_zones_by_price(supply_zones, current_price)
    invalidation = _to_payload_dict(structure_dict.get("invalidation"))

    lines = ["## 구조 레벨", ""]
    lines.append(
        f"- **수요 존**: {', '.join(_format_zone_bounds(zone) for zone in demand_zones) if demand_zones else '없음'}"
    )
    lines.append(
        f"- **공급 존**: {', '.join(_format_zone_bounds(zone) for zone in active_supply) if active_supply else '없음'}"
    )
    lines.append(
        f"- **흡수 공급 존**: {', '.join(_format_zone_bounds(zone) for zone in absorbed_supply) if absorbed_supply else '없음'}"
    )
    lines.append(
        f"- **밸런스 존**: {', '.join(_format_zone_bounds(zone) for zone in balance_zones) if balance_zones else '없음'}"
    )
    lines.append(f"- **무효화 기준**: {invalidation['label'] if invalidation else '없음'}")
    lines.append("")
    return "\n".join(lines)


def _format_execution_levels(execution_levels) -> str:
    if not execution_levels:
        return ""

    lines = ["## 실행 레벨", ""]
    for level in execution_levels:
        level_dict = _to_payload_dict(level)
        lines.append(
            f"- **{level_dict['description']}**: ${level_dict['price']:.2f} ({level_dict['distance_pct']:+.1f}%)"
        )
    lines.append("")
    return "\n".join(lines)


def _format_presented_structure(presented_structure) -> str:
    if not presented_structure:
        return ""
    payload = _to_payload_dict(presented_structure)
    blocks = payload.get("cli_blocks") or []
    if not blocks:
        return ""
    text = "\n".join(blocks)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _format_raw_analysis_sections(result: dict) -> str:
    technical = result["technical"]
    tech_summary = result["technical_summary"]
    news_analysis = result.get("news_analysis")
    fundamental = result.get("fundamental")
    fundamental_summary = result.get("fundamental_summary")
    snapshot = technical.indicators or technical.snapshot

    output = ""

    perf_parts = []
    if snapshot.perf_1m is not None:
        perf_parts.append(f"1M: {snapshot.perf_1m:+.2f}%")
    if snapshot.perf_3m is not None:
        perf_parts.append(f"3M: {snapshot.perf_3m:+.2f}%")
    if snapshot.perf_6m is not None:
        perf_parts.append(f"6M: {snapshot.perf_6m:+.2f}%")
    if snapshot.perf_1y is not None:
        perf_parts.append(f"1Y: {snapshot.perf_1y:+.2f}%")
    if perf_parts:
        output += f"**퍼포먼스**: {' | '.join(perf_parts)}\n\n"

    output += "## 원시 데이터\n\n"
    output += "### 기술적 지표\n\n"

    if snapshot.sma_20 is not None:
        output += f"- **20일 이동평균선**: ${snapshot.sma_20:.2f}\n"
    if snapshot.sma_50 is not None:
        output += f"- **50일 이동평균선**: ${snapshot.sma_50:.2f}\n"
    if snapshot.sma_150 is not None:
        output += f"- **150일 이동평균선**: ${snapshot.sma_150:.2f}\n"
    if snapshot.sma_200 is not None:
        output += f"- **200일 이동평균선**: ${snapshot.sma_200:.2f}\n"

    output += "\n"

    if snapshot.rsi is not None:
        output += f"- **RSI (14일)**: {snapshot.rsi:.1f}\n"
    if snapshot.crsi is not None:
        output += f"- **Cycle RSI**: {snapshot.crsi:.1f}"
        if snapshot.crsi_high_band is not None and snapshot.crsi_low_band is not None:
            output += f" (밴드: {snapshot.crsi_low_band:.1f} - {snapshot.crsi_high_band:.1f})"
        output += "\n"
    if snapshot.macd is not None:
        output += f"- **MACD**: {snapshot.macd:.2f}"
        if snapshot.macd_signal is not None:
            output += f" (시그널: {snapshot.macd_signal:.2f})"
        output += "\n"

    output += "\n"

    if snapshot.adx is not None:
        output += f"- **ADX (추세 강도)**: {snapshot.adx:.1f}\n"

    if snapshot.supertrend_direction is not None:
        direction = "상승" if snapshot.supertrend_direction == 1 else "하락"
        output += f"- **Supertrend**: {direction}"

        if technical.components and "supertrend" in technical.components:
            supertrend_metrics = technical.components["supertrend"]["metrics"]
            if "supertrend_value" in supertrend_metrics:
                st_value = supertrend_metrics["supertrend_value"]
                output += f" (라인: ${st_value:.2f})"
                distance = ((snapshot.price - st_value) / st_value) * 100
                if abs(distance) > 0.1:
                    output += f", 현재가 대비 {distance:+.2f}%"

        output += "\n"

    output += "\n"

    if snapshot.pivot is not None:
        output += f"- **피봇 포인트**: ${snapshot.pivot:.2f}\n"
    if snapshot.support_s1 is not None:
        output += f"- **지지선 S1**: ${snapshot.support_s1:.2f}\n"
    if snapshot.resistance_r1 is not None:
        output += f"- **저항선 R1**: ${snapshot.resistance_r1:.2f}\n"
    if snapshot.high_52w is not None:
        output += f"- **52주 최고가**: ${snapshot.high_52w:.2f}\n"
    if snapshot.low_52w is not None:
        output += f"- **52주 최저가**: ${snapshot.low_52w:.2f}\n"

    output += "\n"

    output += "### 기술 요약\n\n"
    output += f"**총점**: {technical.total_score}\n\n"
    output += f"**요약**: {tech_summary.summary}\n\n"
    output += f"**추천**: {tech_summary.recommendation} (신뢰도: {tech_summary.confidence * 100:.0f}%)\n\n"
    output += f"**근거**: {tech_summary.rationale}\n\n"

    if tech_summary.key_insights:
        output += "**핵심 인사이트**:\n"
        for insight in tech_summary.key_insights:
            output += f"- {insight}\n"
        output += "\n"

    if fundamental and fundamental_summary:
        output += "## Fundamental Analysis\n\n"
        output += "### Key Metrics\n\n"

        output += f"**Sector/Industry**: {fundamental.sector or 'N/A'} / {fundamental.industry or 'N/A'}\n\n"

        priority_metrics = SectorMetrics.get_priority_metrics(fundamental.sector or "")

        for metric_name in priority_metrics:
            value = getattr(fundamental, metric_name, None)
            display_name = _get_metric_display_name(metric_name)
            formatted = _format_metric_value(metric_name, value)
            output += f"⭐ **{display_name}**: {formatted}\n\n"

        output += "\n"

        all_metric_names = [
            "market_cap",
            "pe_ratio",
            "forward_pe",
            "peg_ratio",
            "pb_ratio",
            "ps_ratio",
            "ev_ebitda",
            "roe",
            "roa",
            "gross_margin",
            "operating_margin",
            "profit_margin",
            "revenue_growth",
            "earnings_growth",
            "debt_to_equity",
            "current_ratio",
            "quick_ratio",
            "free_cash_flow",
            "operating_cash_flow",
            "fcf_yield",
            "dividend_yield",
            "payout_ratio",
        ]

        remaining_metrics = [m for m in all_metric_names if m not in priority_metrics]

        for metric_name in remaining_metrics:
            value = getattr(fundamental, metric_name, None)
            display_name = _get_metric_display_name(metric_name)
            formatted = _format_metric_value(metric_name, value)
            output += f"- **{display_name}**: {formatted}\n"

        output += "\n"

        if fundamental.quarterly_data is not None and len(fundamental.quarterly_data) > 0:
            output += "### 분기별 실적\n\n"
            output += "**매출 추이:**\n\n"
            for q in fundamental.quarterly_data:
                if q.revenue is not None:
                    revenue_str = f"${q.revenue / 1e9:.2f}B"
                    yoy_str = _format_growth_rate(q.revenue_yoy)
                    qoq_str = _format_growth_rate(q.revenue_qoq)
                    output += f"- {q.period}: {revenue_str} (YoY {yoy_str}, QoQ {qoq_str})\n"

            output += "\n"
            output += "**이익 추이:**\n\n"
            for q in fundamental.quarterly_data:
                if q.earnings is not None:
                    earnings_str = f"${q.earnings / 1e9:.2f}B"
                    yoy_str = _format_growth_rate(q.earnings_yoy)
                    qoq_str = _format_growth_rate(q.earnings_qoq)
                    output += f"- {q.period}: {earnings_str} (YoY {yoy_str}, QoQ {qoq_str})\n"

            output += "\n"

        if fundamental.quarterly_data is not None:
            eps_quarters = [q for q in fundamental.quarterly_data if q.eps is not None]
            if eps_quarters:
                output += "**분기 EPS 추이:**\n\n"
                for q in eps_quarters:
                    yoy_str = _format_growth_rate(q.eps_yoy)
                    output += f"- {q.period}: EPS {q.eps:,.2f} (YoY {yoy_str})\n"
                output += "\n"

        annual_data = getattr(fundamental, "annual_data", None)
        if annual_data is not None and len(annual_data) > 0:
            output += "**연간 EPS 추이:**\n\n"
            for a in annual_data:
                if a.eps is not None:
                    output += f"- {a.year}: EPS {a.eps:,.2f}\n"
            output += "\n"

        output += "### LLM Analysis\n\n"
        output += f"**Summary**: {fundamental_summary.summary}\n\n"
        output += f"**Valuation**: {fundamental_summary.valuation_assessment} (신뢰도: {fundamental_summary.confidence * 100:.0f}%)\n\n"

        if fundamental_summary.strengths:
            output += "**Strengths**:\n"
            for strength in fundamental_summary.strengths:
                output += f"- {strength}\n"
            output += "\n"

        if fundamental_summary.weaknesses:
            output += "**Weaknesses**:\n"
            for weakness in fundamental_summary.weaknesses:
                output += f"- {weakness}\n"
            output += "\n"

    if news_analysis:
        output += "## News Analysis\n\n"
        output += f"**Sentiment**: {news_analysis.sentiment} (신뢰도: {news_analysis.confidence * 100:.0f}%)\n\n"
        output += f"**Summary**: {news_analysis.summary}\n\n"
        output += f"**Impact Assessment**: {news_analysis.impact_assessment}\n\n"

        if news_analysis.key_themes:
            output += "**Key Themes**: " + ", ".join(news_analysis.key_themes) + "\n\n"

    disclosure = result.get("disclosure")
    if disclosure:
        output += "## 공시 분석\n\n"
        output += f"최근 3개월 주요 공시 {len(disclosure)}건:\n\n"
        for i, item in enumerate(disclosure, 1):
            display_title = _format_disclosure_title(item.form_type, item.description)
            output += f"{i}. **[{item.form_type}] {display_title}** ({item.date})\n"
            output += f"   → [공시 원문 보기]({item.url})\n\n"

    flow = result.get("flow")
    if flow:
        output += "## 수급 동향\n\n"
        output += "| 투자자 | 1일 | 5일 | 10일 | 10일 순매수 일수 |\n"
        output += "|--------|-----|-----|------|------------------|\n"
        output += (
            f"| 외국인 "
            f"| {flow.foreign_direction_1d} ({flow.foreign_net_1d:+,}) "
            f"| {flow.foreign_direction_5d} ({flow.foreign_net_5d:+,}) "
            f"| {flow.foreign_direction_10d} ({flow.foreign_net_10d:+,}) "
            f"| {flow.foreign_buy_days}/10일 |\n"
        )
        output += (
            f"| 기관 "
            f"| {flow.institution_direction_1d} ({flow.institution_net_1d:+,}) "
            f"| {flow.institution_direction_5d} ({flow.institution_net_5d:+,}) "
            f"| {flow.institution_direction_10d} ({flow.institution_net_10d:+,}) "
            f"| {flow.institution_buy_days}/10일 |\n"
        )
        output += "\n"

    return output


def _format_criteria_section(verdict) -> str:
    """CriteriaVerdict를 포지션 플랜 / 청산 판단 섹션으로 렌더링 (게이트·CAN SLIM 제외 — Task 10/11로 이동)."""
    out = "## 📋 포지션 플랜 / 청산 판단\n\n"

    # 포지션 플랜 (미보유 + 게이트 통과 시)
    position_plan = verdict.position_plan
    if position_plan is not None and position_plan.error is None:
        out += "**포지션 플랜**:\n\n"
        out += f"- 진입가: {position_plan.entry:.2f}\n"
        out += f"- 손절가: {position_plan.stop:.2f} ({position_plan.stop_basis})\n"
        if position_plan.shares is not None:
            out += f"- 수량: {position_plan.shares}주\n"
        if position_plan.position_value is not None:
            out += f"- 포지션 금액: {position_plan.position_value:,.0f}\n"
        if position_plan.weight_pct is not None:
            out += f"- 자본 비중: {position_plan.weight_pct:.1f}%\n"
        for label, price in position_plan.r_targets.items():
            out += f"- 목표 {label}: {price:.2f}\n"
        out += "\n"

    # 매도 판정 (보유 시)
    exit_verdict = verdict.exit_verdict
    if exit_verdict is not None:
        action_label = {"liquidate": "청산", "reduce": "비중축소", "hold": "보유유지"}.get(
            exit_verdict.action, exit_verdict.action
        )
        out += f"**보유 판정**: {action_label}\n\n"
        out += f"- 세부사항: {exit_verdict.detail}\n"
        if exit_verdict.current_r is not None:
            out += f"- 현재 R: {exit_verdict.current_r:.2f}R\n"
        if exit_verdict.trailing_stop is not None:
            out += f"- 추적 손절가: {exit_verdict.trailing_stop:.2f}\n"
        out += "\n"

    return out


# ---------------------------------------------------------------------------
# New section formatters (Task 10-15) — added in subsequent tasks
# ---------------------------------------------------------------------------


def _format_summary_section(
    *, gate, relative_strength, high_52w, price, ud_volume_ratio, atr, perf_3m, perf_1y
) -> str:
    """Summary: 핵심 신호 pass/fail(부연) + 핵심 수치 + 퍼포먼스."""
    lines = ["## 📊 Summary", ""]
    if gate is not None:
        sym = {True: "✅", False: "❌", None: "—"}
        checks = gate.checklist if hasattr(gate, "checklist") else []
        quality_grade = gate.quality_grade if hasattr(gate, "quality_grade") else None
        gate_parts = [f"{c.name}{sym[c.met]}" for c in checks if c.required]
        grade = f" · 등급 {quality_grade}" if quality_grade else ""
        lines.append(f"**핵심 기준**: {' '.join(gate_parts)}{grade}")
        for c in checks:
            if c.required:
                lines.append(f"- {c.name}: {c.reason}")
        lines.append("")
    metrics = []
    if relative_strength is not None:
        metrics.append(f"Mansfield RS {relative_strength.mansfield_rs:+.1f}")
    if high_52w and high_52w > 0:
        metrics.append(f"52주 고점 대비 {(price - high_52w) / high_52w * 100:+.1f}%")
    if ud_volume_ratio is not None:
        metrics.append(f"U/D 거래량 {ud_volume_ratio:.1f}")
    if atr is not None:
        metrics.append(f"ATR {atr:.2f}")
    if metrics:
        lines.append("**핵심 수치**: " + " | ".join(metrics))
    perf = []
    if perf_3m is not None:
        perf.append(f"3M {perf_3m:+.1f}%")
    if perf_1y is not None:
        perf.append(f"1Y {perf_1y:+.1f}%")
    if perf:
        lines.append("**퍼포먼스**: " + " | ".join(perf))
    lines.append("")
    return "\n".join(lines) + "\n"


def _format_canslim_section(canslim) -> str:
    """CAN SLIM: 점수 + 미충족 한 줄 + 전 요소 수치."""
    if canslim is None:
        return ""
    order = [
        ("C", canslim.c, "분기 EPS"),
        ("A", canslim.a, "연간 CAGR"),
        ("N", canslim.n, "신요소"),
        ("S", canslim.s, "수급"),
        ("L", canslim.l, "주도주(RS)"),
        ("I", canslim.i, "기관매집"),
        ("M", canslim.m, "시장"),
    ]
    graded = sum(1 for _, e, _ in order if e.met is not None)
    unmet = [(k, lbl) for k, e, lbl in order if e.met is False]
    lines = ["## CAN SLIM", ""]
    header = f"**{canslim.score} / {graded}**"
    if unmet:
        header += " · 미충족: " + ", ".join(f"{k}({lbl})" for k, lbl in unmet)
    lines += [header, ""]
    sym = {True: "✅", False: "❌", None: "—"}
    for k, e, lbl in order:
        lines.append(f"- {sym[e.met]} **{k} {lbl}**: {e.detail or '—'}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _format_stage2_section(*, snapshot_dict, gate_b_reason, supertrend_value) -> str:
    """Stage 2: SMA 값 + 정배열 + Supertrend(방향/라인/gap%)."""
    price = snapshot_dict.get("price")
    lines = ["## Stage 2", ""]
    if gate_b_reason:
        lines += [f"**판정**: {gate_b_reason}", ""]
    for length in (20, 50, 150, 200):
        val = snapshot_dict.get(f"sma_{length}")
        if val is not None:
            lines.append(f"- **SMA {length}**: ${val:.2f}")
    smas = [snapshot_dict.get(f"sma_{n}") for n in (20, 50, 150, 200)]
    if price is not None and all(s is not None for s in smas):
        aligned = price > smas[0] > smas[1] > smas[2] > smas[3]
        lines.append(f"- **배열**: {'정배열' if aligned else '비정배열'} (종가 ${price:.2f})")
    direction = snapshot_dict.get("supertrend_direction")
    if direction is not None:
        line = f"- **Supertrend**: {'상승' if direction == 1 else '하락'}"
        if supertrend_value is not None and price is not None:
            line += f" (라인 ${supertrend_value:.2f}, 현재가 대비 {(price - supertrend_value) / supertrend_value * 100:+.1f}%)"
        lines.append(line)
    high_52w = snapshot_dict.get("high_52w")
    if high_52w and price is not None and high_52w > 0:
        lines.append(f"- **52주 고점 대비**: {(price - high_52w) / high_52w * 100:+.1f}%")
    lines.append("")
    return "\n".join(lines) + "\n"


def _format_momentum_section(*, snapshot_dict, events) -> str:
    """모멘텀: RSI(다이버전스) + MACD(크로스) + 거래량(U/D·추세) + ADX."""
    lines = ["## 모멘텀", ""]
    rsi = snapshot_dict.get("rsi")
    if rsi is not None:
        state = "과매수" if rsi >= 70 else "과매도" if rsi <= 30 else "중립"
        lines.append(f"- **RSI (14)**: {rsi:.1f} ({state})")
    if events is not None and events.rsi_divergence is not None:
        d = events.rsi_divergence
        kind = "하락(Bearish)" if d.divergence_type == "bearish" else "상승(Bullish)"
        lines.append(f"  - 다이버전스: {kind} — {d.detail} ({d.date})")
    macd = snapshot_dict.get("macd")
    if macd is not None:
        parts = [f"{macd:+.2f}"]
        if snapshot_dict.get("macd_signal") is not None:
            parts.append(f"Signal {snapshot_dict['macd_signal']:+.2f}")
        if snapshot_dict.get("macd_histogram") is not None:
            parts.append(f"Hist {snapshot_dict['macd_histogram']:+.2f}")
        lines.append(f"- **MACD**: {' · '.join(parts)}")
    if events is not None and events.macd_cross is not None:
        c = events.macd_cross
        lines.append(
            f"  - {'골든크로스' if c.cross_type == 'golden' else '데드크로스'}: {c.date} ({c.days_ago}일 전)"
        )
    if events is not None:
        if events.ud_volume_ratio is not None:
            lines.append(
                f"- **U/D Volume Ratio**: {events.ud_volume_ratio:.1f} (상승일/하락일 거래량, 50일)"
            )
        if events.volume_trend is not None:
            lines.append(f"- **거래량 추세**: {events.volume_trend} (20일 vs 50일 평균)")
    adx = snapshot_dict.get("adx")
    if adx is not None:
        strength = "강함" if adx >= 25 else "약함" if adx < 20 else "보통"
        lines.append(f"- **ADX (추세 강도)**: {adx:.1f} ({strength})")
    lines.append("")
    return "\n".join(lines) + "\n"


def _format_event_section(*, events, chart_patterns) -> str:
    """Event: 가격 사건 + RS 전환 + 차트패턴(완성 날짜)."""
    lines = ["## Event", ""]
    has_any = False
    if events is not None:
        for pe in events.price_events:
            has_any = True
            when = f" ({pe.date})" if pe.date else ""
            lines.append(f"- **{pe.headline}**: {pe.detail}{when}")
        if events.rs_event is not None:
            has_any = True
            r = events.rs_event
            lines.append(f"- **RS {r.cross_type}**: {r.detail} ({r.date}, {r.days_ago}일 전)")
    if isinstance(chart_patterns, dict):
        for item in chart_patterns.values():
            payload = item if isinstance(item, dict) else item.model_dump()
            if not payload.get("detected"):
                continue
            has_any = True
            days_ago = payload.get("days_ago")
            timing = (
                "오늘 완성"
                if days_ago == 0
                else f"{days_ago}일 전 완성"
                if isinstance(days_ago, int)
                else "완성 시점 미확인"
            )
            completed = payload.get("completed_date")
            when = f" ({completed})" if completed else ""
            lines.append(
                f"- **{payload.get('pattern_name', '패턴')}**: {timing}{when} | {payload.get('description', '')}"
            )
    if not has_any:
        lines.append("- 감지된 사건 없음")
    lines.append("")
    return "\n".join(lines) + "\n"


def _format_structure_section(*, structure_levels, presented_structure, snapshot_dict) -> str:
    """구조 레벨: 수요/공급/밸런스 존 + Pivot/S1/R1."""
    parts = []
    if presented_structure:
        parts.append(_format_presented_structure(presented_structure))
    elif structure_levels:
        parts.append(_format_structure_levels(structure_levels, snapshot_dict.get("price", 0.0)))
    else:
        parts.append("## 구조 레벨\n")
    pivot, s1, r1 = (
        snapshot_dict.get("pivot"),
        snapshot_dict.get("support_s1"),
        snapshot_dict.get("resistance_r1"),
    )
    if any(v is not None for v in (pivot, s1, r1)):
        pl = ["**피봇 레벨**:"]
        if pivot is not None:
            pl.append(f"- 피봇: ${pivot:.2f}")
        if s1 is not None:
            pl.append(f"- 지지 S1: ${s1:.2f}")
        if r1 is not None:
            pl.append(f"- 저항 R1: ${r1:.2f}")
        parts.append("\n".join(pl) + "\n")
    return "\n".join(parts) + "\n"


def _format_debate_section(bundle) -> str:
    """Bull/Bear 논쟁 종합 판정 — 유일한 결론."""
    if bundle is None:
        return ""
    v = bundle.verdict
    lines = [
        "## 🧭 종합 판정",
        "",
        f"- **액션**: {v.action} | **확신도**: {v.confidence * 100:.0f}%",
        f"- **결정적 변수**: {v.swing_factor}",
        "",
        "## 🟢 Bull 논거",
        f"_{bundle.bull_case.thesis}_",
    ]
    lines += [f"- {p}" for p in bundle.bull_case.points]
    lines += ["", "## 🔴 Bear 논거", f"_{bundle.bear_case.thesis}_"]
    lines += [f"- {p}" for p in bundle.bear_case.points]
    lines += ["", "## ⚖️ 판결 사유", v.reconciliation, ""]
    return "\n".join(lines) + "\n"


def _format_ledger_fallback(ledger) -> str:
    """LLM 실패 시 — 결정적 증거 장부만 표시 (spec §10)."""
    if ledger is None:
        return ""
    lines = [
        "## 🧭 종합 판정 (LLM 미생성 — 증거 요약)",
        "",
        f"- Bull 가중치 {ledger.bull_weight} vs Bear 가중치 {ledger.bear_weight}",
        "",
        "**Bull 증거**",
    ]
    lines += [f"- {e.headline}: {e.detail} (가중치 {e.weight})" for e in ledger.bull] or ["- 없음"]
    lines += ["", "**Bear 증거**"]
    lines += [f"- {e.headline}: {e.detail} (가중치 {e.weight})" for e in ledger.bear] or ["- 없음"]
    lines.append("")
    return "\n".join(lines) + "\n"


def format_deep_dive_output(result: dict) -> str:
    """Format deep dive result as markdown (구조화 레이아웃, 결론 없음 — 플랜 A)."""
    ticker = result["ticker"]
    technical = result["technical"]
    snapshot = technical.indicators or technical.snapshot
    snapshot_dict = snapshot.model_dump()
    criteria_verdict = result.get("criteria_verdict")
    events = result.get("momentum_events")
    chart_patterns = result.get("chart_patterns")
    presented_structure = result.get("presented_structure")
    structure_levels = result.get("structure_levels")

    output = f"# Deep Dive Analysis: {ticker}\n\n"
    output += f"## 가격: ${snapshot.price:.2f} ({snapshot.change_pct:+.2f}%)\n\n"

    # 종합 판정 (유일한 결론) — debate 있으면 평결, 없으면 ledger 요약
    debate_bundle = result.get("debate")
    if debate_bundle is not None:
        output += _format_debate_section(debate_bundle)
    elif result.get("debate_ledger") is not None:
        output += _format_ledger_fallback(result["debate_ledger"])

    gate = criteria_verdict.gate if criteria_verdict and hasattr(criteria_verdict, "gate") else None
    rs = criteria_verdict.relative_strength if criteria_verdict else None
    output += _format_summary_section(
        gate=gate,
        relative_strength=rs,
        high_52w=snapshot.high_52w,
        price=snapshot.price,
        ud_volume_ratio=events.ud_volume_ratio if events else None,
        atr=snapshot.atr,
        perf_3m=snapshot.perf_3m,
        perf_1y=snapshot.perf_1y,
    )
    if criteria_verdict and criteria_verdict.canslim:
        output += _format_canslim_section(criteria_verdict.canslim)

    gate_b_reason = None
    if gate is not None:
        checks = gate.checklist if hasattr(gate, "checklist") else []
        gb = next((c for c in checks if c.name == "B"), None)
        gate_b_reason = gb.reason if gb else None
    supertrend_value = None
    if technical.components and "supertrend" in technical.components:
        supertrend_value = technical.components["supertrend"]["metrics"].get("supertrend_value")
    output += _format_stage2_section(
        snapshot_dict=snapshot_dict,
        gate_b_reason=gate_b_reason,
        supertrend_value=supertrend_value,
    )
    output += _format_momentum_section(snapshot_dict=snapshot_dict, events=events)
    output += _format_event_section(events=events, chart_patterns=chart_patterns)
    output += _format_structure_section(
        structure_levels=structure_levels,
        presented_structure=presented_structure,
        snapshot_dict=snapshot_dict,
    )

    factor_assessments = result.get("factor_assessments", [])
    scenarios = result.get("scenarios", [])
    output += "## 📊 증거 상세\n\n"
    if criteria_verdict is not None:
        output += _format_criteria_section(criteria_verdict)
    if factor_assessments:
        output += _format_factor_section(factor_assessments) + "\n"
    if scenarios:
        output += _format_scenario_section(scenarios) + "\n"

    output += "\n"
    output += _format_raw_analysis_sections(result)
    return output
