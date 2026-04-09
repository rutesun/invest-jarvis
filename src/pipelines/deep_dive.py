import logging
from langchain_core.language_models import BaseChatModel
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.news import NewsTool, NewsArticle
from src.tools.fundamental import FundamentalTool, FundamentalSnapshot
from src.tools.technical.models import TechnicalResult
from src.llm import analyzer
from src.llm.analyzer import generate_fundamental_summary
from src.llm.models import (
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    FundamentalSummaryInput,
    FundamentalSummaryOutput,
)

logger = logging.getLogger(__name__)


class DeepDivePipeline:
    """Deep dive analysis pipeline with LLM integration."""

    def __init__(
        self,
        technical_tool: TechnicalAnalysisTool,
        news_tool: NewsTool,
        llm: BaseChatModel,
        fundamental_tool: FundamentalTool | None = None,
    ):
        self.technical_tool = technical_tool
        self.news_tool = news_tool
        self.llm = llm
        self.fundamental_tool = fundamental_tool

    async def run(self, ticker: str) -> dict:
        """Run deep dive analysis for a ticker.

        Returns:
            dict with keys:
                - ticker: str
                - technical: TechnicalResult
                - technical_summary: TechnicalSummaryOutput
                - news: list[NewsArticle]
                - news_analysis: NewsAnalysisOutput | None
                - fundamental: FundamentalSnapshot | None
                - fundamental_summary: FundamentalSummaryOutput | None
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

        fundamental_data = None
        fundamental_summary = None
        if self.fundamental_tool:
            fund_result = await self.fundamental_tool.execute(ticker)
            if fund_result.success:
                fundamental_data = fund_result.data
                fundamental_summary = await self._generate_fundamental_summary(ticker, fundamental_data)
            else:
                logger.warning(f"Fundamental data fetch failed for {ticker}: {fund_result.error}")

        return {
            "ticker": ticker,
            "technical": technical_data,
            "technical_summary": technical_summary,
            "news": news_articles,
            "news_analysis": news_analysis,
            "fundamental": fundamental_data,
            "fundamental_summary": fundamental_summary,
        }

    async def _generate_technical_summary(
        self, technical_data: TechnicalResult
    ) -> TechnicalSummaryOutput:
        """Generate LLM summary of technical analysis."""
        # Support both old (strategies) and new (components) formats
        if technical_data.strategies:
            # Legacy strategy-based format
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
        else:
            # New component-based format
            strategies = [
                {
                    "name": name,
                    "status": "N/A",
                    "confidence": 0,
                    "signals": comp["signals"],
                    "evidence": comp["evidence"],
                    "metrics": comp["metrics"],
                }
                for name, comp in technical_data.components.items()
            ]

        # Get snapshot from either indicators or snapshot field
        snapshot = technical_data.indicators or technical_data.snapshot

        indicators = {}
        if snapshot.sma_20 is not None:
            indicators["sma_20"] = snapshot.sma_20
        if snapshot.sma_50 is not None:
            indicators["sma_50"] = snapshot.sma_50
        if snapshot.rsi is not None:
            indicators["rsi"] = snapshot.rsi
        if snapshot.macd is not None:
            indicators["macd"] = snapshot.macd

        input_data = TechnicalSummaryInput(
            ticker=technical_data.ticker or "UNKNOWN",
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

    async def _generate_fundamental_summary(
        self, ticker: str, fundamental_data: FundamentalSnapshot
    ) -> FundamentalSummaryOutput:
        """Generate LLM summary of fundamental analysis."""
        input_data = FundamentalSummaryInput(
            ticker=ticker,
            sector=fundamental_data.sector,
            industry=fundamental_data.industry,
            pe_ratio=fundamental_data.pe_ratio,
            forward_pe=fundamental_data.forward_pe,
            peg_ratio=fundamental_data.peg_ratio,
            ev_ebitda=fundamental_data.ev_ebitda,
            ps_ratio=fundamental_data.ps_ratio,
            roe=fundamental_data.roe,
            revenue_growth=fundamental_data.revenue_growth,
            earnings_growth=fundamental_data.earnings_growth,
            debt_to_equity=fundamental_data.debt_to_equity,
            free_cash_flow=fundamental_data.free_cash_flow,
            fcf_yield=fundamental_data.fcf_yield,
            gross_margin=fundamental_data.gross_margin,
            operating_margin=fundamental_data.operating_margin,
        )

        return await generate_fundamental_summary(input_data, self.llm)
