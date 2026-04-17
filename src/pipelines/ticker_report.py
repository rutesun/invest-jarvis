from datetime import datetime
from langchain_core.language_models import BaseChatModel
from src.tools.macro import MacroTool, TickerMacroSnapshot
from src.tools.technical.tool import TechnicalAnalysisTool


class TickerReportPipeline:
    """Ticker-based report pipeline with macro snapshot and technical analysis."""

    def __init__(
        self,
        macro_tool: MacroTool,
        technical_tool: TechnicalAnalysisTool,
        llm: BaseChatModel,
    ):
        self.macro_tool = macro_tool
        self.technical_tool = technical_tool
        self.llm = llm

    async def run(self, tickers: list[str]) -> dict:
        """Run daily market report for multiple tickers.

        Returns:
            dict with keys:
                - date: datetime
                - macro: TickerMacroSnapshot
                - tickers: list[dict] with keys:
                    - ticker: str
                    - technical: TechnicalResult | None
                    - error: str | None
        """
        macro_result = await self.macro_tool.execute()
        if not macro_result.success:
            raise RuntimeError(f"Macro snapshot failed: {macro_result.error}")

        macro_data: TickerMacroSnapshot = macro_result.data

        ticker_analyses = []
        for ticker in tickers:
            analysis = await self._analyze_ticker(ticker)
            ticker_analyses.append(analysis)

        return {
            "date": datetime.now(),
            "macro": macro_data,
            "tickers": ticker_analyses,
        }

    async def _analyze_ticker(self, ticker: str) -> dict:
        """Analyze a single ticker.

        Returns:
            dict with keys:
                - ticker: str
                - technical: TechnicalResult | None
                - error: str | None
        """
        tech_result = await self.technical_tool.execute(ticker)

        if not tech_result.success:
            return {
                "ticker": ticker,
                "technical": None,
                "error": tech_result.error,
            }

        return {
            "ticker": ticker,
            "technical": tech_result.data,
            "error": None,
        }
