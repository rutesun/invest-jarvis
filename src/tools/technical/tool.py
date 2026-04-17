import logging

from src.core.interfaces import BaseProvider, BaseTool
from src.core.models import ToolResult
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer


logger = logging.getLogger(__name__)


class TechnicalAnalysisTool(BaseTool):
    """Technical analysis tool using component-based scoring."""

    name = "technical"
    description = "기술적 분석 도구 (추세, 모멘텀, 패턴)"

    def __init__(self, provider: BaseProvider, scorer: TechnicalScorer):
        self.provider = provider
        self.scorer = scorer
        self.calculator = IndicatorCalculator()

    async def execute(self, ticker: str, period: str = "1y", **kwargs) -> ToolResult:
        """Execute technical analysis on ticker."""
        try:
            logger.debug("Fetching price history: %s (period=%s)", ticker, period)
            df = await self.provider.get_price_history(ticker, period)
            if df.empty:
                logger.debug("No price data returned for %s", ticker)
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"No data found for {ticker}",
                )

            logger.debug("Got %d rows for %s, calculating indicators", len(df), ticker)
            df = self.calculator.calculate(df)

            logger.debug("Scoring %s", ticker)
            technical_result = self.scorer.score(df, ticker=ticker)
            logger.debug("Score for %s: %s", ticker, technical_result.total_score)

            return ToolResult(success=True, data=technical_result)

        except Exception as e:
            logger.debug("Technical analysis error for %s: %s", ticker, e)
            return ToolResult(success=False, data=None, error=str(e))
