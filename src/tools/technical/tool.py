from datetime import datetime
from src.core.interfaces import BaseTool, BaseProvider
from src.core.models import ToolResult
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.models import TechnicalResult


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
            # Get price history
            df = await self.provider.get_price_history(ticker, period)
            if df.empty:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"No data found for {ticker}",
                )

            # Calculate indicators
            df = self.calculator.calculate(df)

            # Score with components
            technical_result = self.scorer.score(df, ticker=ticker)

            return ToolResult(success=True, data=technical_result)

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
