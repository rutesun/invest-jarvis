from typing import Any
from src.tools.portfolio import PortfolioTool
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.news import NewsTool


class PortfolioPipeline:
    """Portfolio monitoring pipeline."""

    def __init__(
        self,
        portfolio_tool: PortfolioTool,
        technical_tool: TechnicalAnalysisTool,
        news_tool: NewsTool,
    ):
        self.portfolio_tool = portfolio_tool
        self.technical_tool = technical_tool
        self.news_tool = news_tool

    async def run(self) -> dict[str, Any]:
        """Run portfolio monitoring."""
        portfolio_result = await self.portfolio_tool.execute()
        if not portfolio_result.success:
            return {
                "success": False,
                "error": portfolio_result.error,
            }

        balance = portfolio_result.data
        holdings = []

        for position in balance.get("positions", []):
            ticker = position["ticker"]

            tech_result = await self.technical_tool.execute(ticker)
            technical = tech_result.data if tech_result.success else None

            news_result = await self.news_tool.execute(ticker, limit=3)
            news = news_result.data if news_result.success else []

            holdings.append({
                "ticker": ticker,
                "name": position["name"],
                "quantity": position["quantity"],
                "current_price": position["current_price"],
                "profit_loss": position.get("profit_loss", 0),
                "profit_loss_pct": position.get("profit_loss_pct", 0),
                "technical": technical,
                "news": news,
            })

        return {
            "success": True,
            "total_assets": balance["total_assets"],
            "cash": balance.get("cash", 0),
            "stock_value": balance.get("stock_value", 0),
            "holdings": holdings,
        }

    def format_output(self, result: dict[str, Any]) -> str:
        """Format portfolio result as readable string."""
        if not result.get("success", False):
            return f"Error: {result.get('error', 'Unknown error')}"

        lines = [
            f"## Portfolio Summary",
            "",
            f"**Total Assets**: ₩{result['total_assets']:,.0f}",
            f"**Cash**: ₩{result.get('cash', 0):,.0f}",
            f"**Stock Value**: ₩{result.get('stock_value', 0):,.0f}",
            "",
            "### Holdings",
            "",
        ]

        for holding in result.get("holdings", []):
            lines.append(f"#### {holding['name']} ({holding['ticker']})")
            lines.append(f"- Quantity: {holding['quantity']}")
            lines.append(f"- Current: ₩{holding['current_price']:,.0f}")
            lines.append(f"- P&L: ₩{holding.get('profit_loss', 0):,.0f} ({holding.get('profit_loss_pct', 0):+.2f}%)")

            if holding.get("technical"):
                tech = holding["technical"]
                lines.append(f"- Assessment: {tech.overall_assessment} (신뢰도: {tech.confidence_score:.0f}%)")
                if tech.key_insights:
                    lines.append(f"- Insights: {', '.join(tech.key_insights[:2])}")

            lines.append("")

        return "\n".join(lines)
