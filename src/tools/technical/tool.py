from datetime import datetime
from src.core.interfaces import BaseTool, BaseProvider
from src.core.models import ToolResult
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.models import TechnicalResult


class TechnicalAnalysisTool(BaseTool):
    """Technical analysis tool using multiple strategies."""

    name = "technical"
    description = "기술적 분석 도구 (추세, 모멘텀, 패턴)"

    def __init__(self, provider: BaseProvider, registry: StrategyRegistry):
        self.provider = provider
        self.registry = registry
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
            indicators = self.calculator.create_snapshot(df)

            # Run strategies
            strategy_results = []
            total_confidence = 0
            signals_count = {"강세": 0, "약세": 0, "중립": 0}

            for strategy in self.registry.get_all():
                result = strategy.analyze(df)
                strategy_results.append(result)
                total_confidence += result.confidence

                if "강세" in result.status:
                    signals_count["강세"] += 1
                elif "약세" in result.status:
                    signals_count["약세"] += 1
                else:
                    signals_count["중립"] += 1

            # Determine overall assessment
            if signals_count["강세"] > signals_count["약세"]:
                overall = "매수"
            elif signals_count["약세"] > signals_count["강세"]:
                overall = "매도"
            else:
                overall = "중립"

            avg_confidence = total_confidence / len(strategy_results) if strategy_results else 50

            # Collect insights and warnings
            key_insights = []
            warnings = []
            for sr in strategy_results:
                key_insights.extend(sr.signals)
                if sr.confidence < 30:
                    warnings.append(f"{sr.name}: 낮은 신뢰도 ({sr.confidence:.0f}%)")

            technical_result = TechnicalResult(
                ticker=ticker,
                timestamp=datetime.now(),
                indicators=indicators,
                strategies=strategy_results,
                overall_assessment=overall,
                confidence_score=avg_confidence,
                key_insights=key_insights,
                warnings=warnings,
            )

            return ToolResult(success=True, data=technical_result)

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
