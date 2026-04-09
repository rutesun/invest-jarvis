from langchain_core.language_models import BaseChatModel
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.news import NewsTool, NewsArticle
from src.tools.technical.models import TechnicalResult
from src.llm import analyzer
from src.llm.models import (
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
    NewsAnalysisInput,
    NewsAnalysisOutput,
)


class DeepDivePipeline:
    """Deep dive analysis pipeline with LLM integration."""

    def __init__(
        self,
        technical_tool: TechnicalAnalysisTool,
        news_tool: NewsTool,
        llm: BaseChatModel,
    ):
        self.technical_tool = technical_tool
        self.news_tool = news_tool
        self.llm = llm

    async def run(self, ticker: str) -> dict:
        """Run deep dive analysis for a ticker.

        Returns:
            dict with keys:
                - ticker: str
                - technical: TechnicalResult
                - technical_summary: TechnicalSummaryOutput
                - news: list[NewsArticle]
                - news_analysis: NewsAnalysisOutput | None
        """
        tech_result = await self.technical_tool.execute(ticker)
        if not tech_result.success:
            raise RuntimeError(f"Technical analysis failed: {tech_result.error}")

        technical_data: TechnicalResult = tech_result.data

        news_result = await self.news_tool.execute(ticker, limit=10)
        if not news_result.success:
            raise RuntimeError(f"News fetch failed: {news_result.error}")

        news_articles: list[NewsArticle] = news_result.data

        technical_summary = await self._generate_technical_summary(technical_data)

        news_analysis = None
        if news_articles:
            news_analysis = await self._analyze_news(ticker, news_articles)

        return {
            "ticker": ticker,
            "technical": technical_data,
            "technical_summary": technical_summary,
            "news": news_articles,
            "news_analysis": news_analysis,
        }

    async def _generate_technical_summary(
        self, technical_data: TechnicalResult
    ) -> TechnicalSummaryOutput:
        """Generate LLM summary of technical analysis."""
        strategies = [
            {
                "name": s.name,
                "status": s.status,
                "confidence": s.confidence,
                "signals": s.signals,
                "evidence": s.evidence,
                "metrics": s.metrics,
            }
            for s in technical_data.strategies
        ]

        indicators = {}
        snapshot = technical_data.indicators
        if snapshot.sma_20:
            indicators["sma_20"] = snapshot.sma_20
        if snapshot.sma_50:
            indicators["sma_50"] = snapshot.sma_50
        if snapshot.rsi:
            indicators["rsi"] = snapshot.rsi
        if snapshot.macd:
            indicators["macd"] = snapshot.macd

        input_data = TechnicalSummaryInput(
            ticker=technical_data.ticker,
            price=snapshot.price,
            change_pct=snapshot.change_pct,
            strategies=strategies,
            indicators=indicators,
        )

        return await analyzer.generate_technical_summary(input_data, self.llm)

    async def _analyze_news(
        self, ticker: str, news_articles: list[NewsArticle]
    ) -> NewsAnalysisOutput:
        """Analyze news with LLM."""
        news_data = [
            {
                "title": article.title,
                "published": article.published,
                "summary": article.summary,
                "url": article.url,
            }
            for article in news_articles
        ]

        input_data = NewsAnalysisInput(
            ticker=ticker,
            company_name=ticker,
            news=news_data,
        )

        return await analyzer.analyze_news(input_data, self.llm)
