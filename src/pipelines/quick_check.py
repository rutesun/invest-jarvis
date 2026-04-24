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

        return {
            "ticker": ticker,
            "success": True,
            "price": snapshot.price,
            "change_pct": snapshot.change_pct,
            "total_score": tech.total_score,
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

    def format_output(self, result: dict[str, Any]) -> str:
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
            for comp in components:
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
                    # Add blank line after component if it has content
                    if comp.get("signals") or comp.get("evidence"):
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
