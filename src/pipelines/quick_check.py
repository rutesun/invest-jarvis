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
        return {
            "ticker": ticker,
            "success": True,
            "price": tech.indicators.price,
            "change_pct": tech.indicators.change_pct,
            "assessment": tech.overall_assessment,
            "confidence": tech.confidence_score,
            "signals": tech.key_insights,
            "warnings": tech.warnings,
            "indicators": {
                "sma_20": tech.indicators.sma_20,
                "sma_50": tech.indicators.sma_50,
                "rsi": tech.indicators.rsi,
                "adx": tech.indicators.adx,
            },
            "strategies": [
                {
                    "name": s.name,
                    "status": s.status,
                    "confidence": s.confidence,
                    "signals": s.signals,
                }
                for s in tech.strategies
            ],
        }

    def format_output(self, result: dict[str, Any]) -> str:
        """Format result as readable string."""
        if not result.get("success", False):
            return f"Error: {result.get('error', 'Unknown error')}"

        lines = [
            f"## {result['ticker']} Quick Check",
            "",
            f"**가격**: ${result['price']:.2f} ({result['change_pct']:+.2f}%)",
            f"**평가**: {result['assessment']} (신뢰도: {result['confidence']:.0f}%)",
            "",
        ]

        # Indicators
        indicators = result.get("indicators", {})
        lines.append("### 주요 지표")
        if indicators.get("sma_20"):
            lines.append(f"- SMA 20: ${indicators['sma_20']:.2f}")
        if indicators.get("sma_50"):
            lines.append(f"- SMA 50: ${indicators['sma_50']:.2f}")
        if indicators.get("rsi"):
            lines.append(f"- RSI: {indicators['rsi']:.1f}")
        if indicators.get("adx"):
            lines.append(f"- ADX: {indicators['adx']:.1f}")

        # Signals
        if result.get("signals"):
            lines.append("")
            lines.append("### 시그널")
            for signal in result["signals"]:
                lines.append(f"- {signal}")

        # Warnings
        if result.get("warnings"):
            lines.append("")
            lines.append("### 주의")
            for warning in result["warnings"]:
                lines.append(f"- {warning}")

        return "\n".join(lines)
