import asyncio
import logging

from langchain_core.language_models import BaseChatModel

from src.llm import analyzer
from src.llm.analyzer import generate_fundamental_summary
from src.llm.models import (
    FundamentalSummaryInput,
    FundamentalSummaryOutput,
    IntegratedAnalysisInput,
    IntegratedAnalysisOutput,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)
from src.tools.disclosure import DisclosureItem, DisclosureTool, extract_kr_code, is_korean_ticker
from src.tools.flow import FlowTool, InvestorFlow
from src.tools.fundamental import FundamentalSnapshot, FundamentalTool
from src.tools.news import NewsArticle, NewsTool
from src.tools.technical.models import TechnicalResult
from src.tools.technical.tool import TechnicalAnalysisTool


logger = logging.getLogger(__name__)


class DeepDivePipeline:
    """Deep dive analysis pipeline with LLM integration."""

    def __init__(
        self,
        technical_tool: TechnicalAnalysisTool,
        news_tool: NewsTool,
        llm: BaseChatModel,
        fundamental_tool: FundamentalTool | None = None,
        disclosure_tool: DisclosureTool | None = None,
        flow_tool: FlowTool | None = None,
    ):
        self.technical_tool = technical_tool
        self.news_tool = news_tool
        self.llm = llm
        self.fundamental_tool = fundamental_tool
        self.disclosure_tool = disclosure_tool
        self.flow_tool = flow_tool

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
                - disclosure: list[DisclosureItem] | None (SEC 10-Q/8-K or OpenDART)
                - flow: InvestorFlow | None (외국인/기관 순매수 동향, 한국주식만)
                - integrated_analysis: IntegratedAnalysisOutput | None (종합 인사이트)
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
                fundamental_summary = await self._generate_fundamental_summary(
                    ticker, fundamental_data
                )
            else:
                logger.warning(f"Fundamental data fetch failed for {ticker}: {fund_result.error}")

        # 선택적 툴 병렬 실행
        optional_coros = []
        optional_keys: list[str] = []

        if self.disclosure_tool:
            optional_coros.append(self.disclosure_tool.execute(ticker))
            optional_keys.append("disclosure")

        if self.flow_tool and is_korean_ticker(ticker):
            optional_coros.append(self.flow_tool.execute(extract_kr_code(ticker)))
            optional_keys.append("flow")

        optional_data: dict = {}
        if optional_coros:
            opt_results = await asyncio.gather(*optional_coros, return_exceptions=True)
            for key, res in zip(optional_keys, opt_results):
                if not isinstance(res, Exception) and res.success:
                    optional_data[key] = res.data
                else:
                    logger.warning("선택적 툴 '%s' 실패: %s", key, res)
                    optional_data[key] = None

        disclosure_items: list[DisclosureItem] | None = optional_data.get("disclosure")
        flow_data: InvestorFlow | None = optional_data.get("flow")

        # 공시 또는 수급 데이터가 있을 때만 종합 인사이트 생성
        integrated_analysis = None
        if disclosure_items is not None or flow_data is not None:
            integrated_analysis = await self._generate_integrated_analysis(
                ticker=ticker,
                technical_summary=technical_summary,
                fundamental_summary=fundamental_summary,
                disclosure_items=disclosure_items,
                flow_data=flow_data,
            )

        return {
            "ticker": ticker,
            "technical": technical_data,
            "technical_summary": technical_summary,
            "news": news_articles,
            "news_analysis": news_analysis,
            "fundamental": fundamental_data,
            "fundamental_summary": fundamental_summary,
            "disclosure": disclosure_items,
            "flow": flow_data,
            "integrated_analysis": integrated_analysis,
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

    def _format_flow_for_llm(self, flow: InvestorFlow) -> str:
        """InvestorFlow를 LLM 컨텍스트용 마크다운 테이블 문자열로 변환."""
        lines = [
            "| 투자자 | 1일 | 5일 | 10일 | 10일 순매수 일수 |",
            "|--------|-----|-----|------|-----------------|",
            (
                f"| 외국인 "
                f"| {flow.foreign_direction_1d} ({flow.foreign_net_1d:+,}) "
                f"| {flow.foreign_direction_5d} ({flow.foreign_net_5d:+,}) "
                f"| {flow.foreign_direction_10d} ({flow.foreign_net_10d:+,}) "
                f"| {flow.foreign_buy_days}/10일 |"
            ),
            (
                f"| 기관 "
                f"| {flow.institution_direction_1d} ({flow.institution_net_1d:+,}) "
                f"| {flow.institution_direction_5d} ({flow.institution_net_5d:+,}) "
                f"| {flow.institution_direction_10d} ({flow.institution_net_10d:+,}) "
                f"| {flow.institution_buy_days}/10일 |"
            ),
        ]
        return "\n".join(lines)

    async def _generate_integrated_analysis(
        self,
        ticker: str,
        technical_summary: TechnicalSummaryOutput,
        fundamental_summary: FundamentalSummaryOutput | None,
        disclosure_items: list[DisclosureItem] | None,
        flow_data: InvestorFlow | None,
    ) -> IntegratedAnalysisOutput:
        # Convert DisclosureItem objects to dicts for LLM input
        disclosure_dicts = []
        if disclosure_items:
            for item in disclosure_items:
                disclosure_dicts.append(
                    {
                        "form_type": item.form_type,
                        "date": item.date,
                        "description": item.description,
                        "url": item.url,
                    }
                )

        input_data = IntegratedAnalysisInput(
            ticker=ticker,
            technical_recommendation=technical_summary.recommendation,
            technical_rationale=technical_summary.rationale,
            fundamental_valuation=(
                fundamental_summary.valuation_assessment if fundamental_summary else None
            ),
            disclosure_items=disclosure_dicts,
            flow_summary=self._format_flow_for_llm(flow_data) if flow_data else None,
        )
        return await analyzer.generate_integrated_analysis(input_data, self.llm)
