from typing import Any

from src.tools.technical.tool import TechnicalAnalysisTool


class QuickCheckPipeline:
    """Quick check pipeline - technical analysis without LLM."""

    def __init__(self, technical_tool: TechnicalAnalysisTool):
        self.technical_tool = technical_tool

    async def run(self, ticker: str) -> dict[str, Any]:
        """Run quick check analysis."""
        result = await self.technical_tool.execute(ticker)

        if not result.success:
            return {
                "ticker": ticker,
                "error": result.error,
                "success": False,
            }

        tech = result.data

        # Support both old (indicators) and new (snapshot) formats
        snapshot = tech.indicators or tech.snapshot

        # Collect signals from components (new) or key_insights (old)
        signals = []
        if tech.components:
            for comp in tech.components.values():
                signals.extend(comp.get("signals", []))
        elif tech.key_insights:
            signals = tech.key_insights

        # Build strategies/components list
        components_list = []
        if tech.components:
            for name, comp in tech.components.items():
                components_list.append(
                    {
                        "name": name,
                        "score": comp.get("score", 0),
                        "signals": comp.get("signals", []),
                        "evidence": comp.get("evidence", []),
                    }
                )
        elif tech.strategies:
            components_list = [
                {
                    "name": s.name,
                    "status": s.status,
                    "confidence": s.confidence,
                    "signals": s.signals,
                }
                for s in tech.strategies
            ]

        verdict = tech.technical_verdict.model_dump() if tech.technical_verdict else None

        return {
            "ticker": ticker,
            "success": True,
            "price": snapshot.price,
            "change_pct": snapshot.change_pct,
            "total_score": tech.total_score,
            "component_raw_total": tech.component_raw_total,
            "adjusted_score": tech.adjusted_score,
            "technical_verdict": verdict,
            "score_history": [point.model_dump() for point in tech.score_history],
            "score_history_warning": tech.score_history_warning,
            "assessment": tech.overall_assessment or "N/A",
            "confidence": tech.confidence_score or 0,
            "signals": signals[:10],  # Limit to top 10
            "warnings": tech.warnings or [],
            "indicators": {
                "sma_20": snapshot.sma_20,
                "sma_50": snapshot.sma_50,
                "sma_150": snapshot.sma_150,
                "rsi": snapshot.rsi,
                "adx": snapshot.adx,
                "crsi": snapshot.crsi,
            },
            "components": components_list,
        }

    def format_output(self, result: dict[str, Any], detailed_history: bool = False) -> str:
        """Format result as readable string."""
        if not result.get("success", False):
            return f"Error: {result.get('error', 'Unknown error')}"

        lines = [
            f"## {result['ticker']} Quick Check",
            "",
            f"**가격**: ${result['price']:.2f} ({result['change_pct']:+.2f}%)",
            f"**총점**: {result['total_score']}",
            "",
        ]

        if result.get("adjusted_score") is not None:
            lines.append(f"**Adjusted Score**: {result['adjusted_score']}")

        verdict = result.get("technical_verdict")
        if verdict:
            lines.extend(
                [
                    "",
                    "### Technical Verdict",
                    f"- Action: {verdict['action']} ({verdict['entry_mode']}, confidence={verdict['confidence']})",
                    f"- 신규 진입 가능: {'yes' if verdict['new_entry_allowed'] else 'no'}",
                ]
            )
            if verdict.get("reasons"):
                lines.append("- Reasons:")
                lines.extend(f"  - {reason}" for reason in verdict["reasons"])
            if verdict.get("cautions"):
                lines.append("- Cautions:")
                lines.extend(f"  - {caution}" for caution in verdict["cautions"])
            if verdict.get("invalidation_level") is not None:
                lines.append(f"- Invalidation: {verdict['invalidation_level']:.2f}")
            if verdict.get("score_trend_summary"):
                lines.append(f"- Trend: {verdict['score_trend_summary']}")

        history = result.get("score_history") or []
        if history:
            lines.extend(["", "### 최근 점수 추이"])
            previous_point = None
            for point in history:
                if detailed_history:
                    lines.extend(_format_detailed_history_point(point, previous_point))
                else:
                    lines.append(_format_compact_history_point(point, previous_point))
                previous_point = point
        if result.get("score_history_warning"):
            lines.append(f"- score history warning: {result['score_history_warning']}")

        # Performance
        indicators = result.get("indicators", {})
        perf_lines = []
        if indicators.get("perf_1m") is not None:
            perf_lines.append(f"1M: {indicators['perf_1m']:+.2f}%")
        if indicators.get("perf_3m") is not None:
            perf_lines.append(f"3M: {indicators['perf_3m']:+.2f}%")
        if indicators.get("perf_6m") is not None:
            perf_lines.append(f"6M: {indicators['perf_6m']:+.2f}%")
        if indicators.get("perf_1y") is not None:
            perf_lines.append(f"1Y: {indicators['perf_1y']:+.2f}%")
        if perf_lines:
            lines.append(f"**퍼포먼스**: {' | '.join(perf_lines)}")
            lines.append("")

        # Show assessment if available (legacy format)
        if result.get("assessment") and result["assessment"] != "N/A":
            lines.append(f"**평가**: {result['assessment']} (신뢰도: {result['confidence']:.0f}%)")
            lines.append("")

        # Components/Strategies breakdown
        components = result.get("components", [])
        if components:
            lines.append("### 분석 컴포넌트")
            for i, comp in enumerate(components):
                if "score" in comp:  # New format
                    lines.append(f"- **{comp['name']}**: {comp['score']}점")
                    # Show all signals first
                    if comp.get("signals"):
                        for sig in comp["signals"][:3]:  # Top 3 signals per component
                            lines.append(f"  - {sig}")
                    # Then show evidence with clear separation
                    if comp.get("evidence"):
                        if comp.get("signals"):
                            lines.append("")  # Blank line between signals and evidence
                        lines.append("  **근거:**")  # 2-space indent (same level as signals)
                        for ev in comp["evidence"][:5]:  # Top 5 evidence per component
                            lines.append(f"    - {ev}")  # 4-space indent for evidence items
                    # Add blank line between components (not after last one)
                    if (comp.get("signals") or comp.get("evidence")) and i < len(components) - 1:
                        lines.append("")
                else:  # Legacy format
                    lines.append(
                        f"- **{comp['name']}**: {comp.get('status', 'N/A')} ({comp.get('confidence', 0):.0f}%)"
                    )
            lines.append("")

        # Indicators
        indicators = result.get("indicators", {})
        lines.append("### 주요 지표")
        if indicators.get("sma_20"):
            lines.append(f"- SMA 20: ${indicators['sma_20']:.2f}")
        if indicators.get("sma_50"):
            lines.append(f"- SMA 50: ${indicators['sma_50']:.2f}")
        if indicators.get("sma_150"):
            lines.append(f"- SMA 150: ${indicators['sma_150']:.2f}")
        if indicators.get("rsi"):
            lines.append(f"- RSI: {indicators['rsi']:.1f}")
        if indicators.get("crsi"):
            lines.append(f"- cRSI: {indicators['crsi']:.1f}")
        if indicators.get("adx"):
            lines.append(f"- ADX: {indicators['adx']:.1f}")

        # All signals
        if result.get("signals"):
            lines.append("")
            lines.append("### 전체 시그널")
            for signal in result["signals"]:
                lines.append(f"- {signal}")

        # Warnings
        if result.get("warnings"):
            lines.append("")
            lines.append("### 주의")
            for warning in result["warnings"]:
                lines.append(f"- {warning}")

        return "\n".join(lines)


def _format_compact_history_point(
    point: dict[str, Any],
    previous_point: dict[str, Any] | None,
) -> str:
    adjusted = point["adjusted_score"]
    delta = _score_delta(adjusted, previous_point)
    details = []
    drivers = point.get("driver_components") or []
    if drivers:
        details.append(f"driver: {', '.join(drivers)}")
    entry = _entry_transition(point, previous_point)
    if entry:
        details.append(f"entry: {entry}")
    cautions = point.get("cautions") or []
    if cautions:
        details.append(f"caution: {cautions[0]}")

    suffix = f" | {' | '.join(details)}" if details else ""
    return (
        f"- {point['date']}: close {point['close']:.2f}, "
        f"raw {point['component_raw_total']}, adjusted {adjusted}{delta}, "
        f"{point['verdict_action']} — {point['one_line_reason']}{suffix}"
    )


def _format_detailed_history_point(
    point: dict[str, Any],
    previous_point: dict[str, Any] | None,
) -> list[str]:
    adjusted = point["adjusted_score"]
    delta = _score_delta(adjusted, previous_point)
    lines = [
        (
            f"- {point['date']}: close {point['close']:.2f}, "
            f"raw {point['component_raw_total']}, adjusted {adjusted}{delta}, "
            f"{point['verdict_action']}"
        ),
        f"  - reason: {point['one_line_reason']}",
    ]
    drivers = point.get("driver_components") or []
    if drivers:
        lines.append(f"  - driver: {', '.join(drivers)}")
    entry = _entry_transition(point, previous_point)
    if entry:
        lines.append(f"  - entry: {entry}")
    cautions = point.get("cautions") or []
    if cautions:
        lines.append(f"  - caution: {', '.join(cautions)}")
    return lines


def _score_delta(adjusted: int, previous_point: dict[str, Any] | None) -> str:
    if previous_point is None:
        return ""
    delta = adjusted - int(previous_point["adjusted_score"])
    return f" (Δ {delta:+d})"


def _entry_transition(
    point: dict[str, Any],
    previous_point: dict[str, Any] | None,
) -> str | None:
    current = point.get("new_entry_allowed")
    if current is None:
        return None
    current_label = "yes" if current else "no"
    if previous_point is None or previous_point.get("new_entry_allowed") is None:
        return current_label
    previous_label = "yes" if previous_point.get("new_entry_allowed") else "no"
    if previous_label == current_label:
        return current_label
    return f"{previous_label}→{current_label}"
