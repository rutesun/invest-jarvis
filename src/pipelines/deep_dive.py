import asyncio
import logging
from collections.abc import Callable

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
from src.pipelines.analyze_decision import apply_playbook_veto, build_analyze_decision_bundle
from src.tools.criteria.holdings import load_holdings
from src.tools.disclosure import DisclosureItem, DisclosureTool, extract_kr_code, is_korean_ticker
from src.tools.flow import FlowTool, InvestorFlow
from src.tools.fundamental import FundamentalSnapshot, FundamentalTool
from src.tools.news import NewsArticle, NewsTool
from src.tools.technical.charting import render_technical_chart
from src.tools.technical.components.pattern_engine import PatternEngine
from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.models import TechnicalResult
from src.tools.technical.price_levels import get_fibonacci_base_points, identify_key_levels
from src.tools.technical.structure_presentation import build_structure_presentation
from src.tools.technical.structure_zones import StructureZoneDetector
from src.tools.technical.tool import TechnicalAnalysisTool


logger = logging.getLogger(__name__)
_FUNDAMENTAL_SIGNAL_FIELDS = (
    "pe_ratio",
    "forward_pe",
    "peg_ratio",
    "ev_ebitda",
    "ps_ratio",
    "roe",
    "roa",
    "revenue_growth",
    "earnings_growth",
    "gross_margin",
    "operating_margin",
    "profit_margin",
    "debt_to_equity",
    "free_cash_flow",
    "fcf_yield",
    "dividend_yield",
    "payout_ratio",
)


def _compute_eps_cagr(newest: float, oldest: float, n_years: int) -> float | None:
    """Annual EPS CAGR for a given period.

    Returns None when CAGR is mathematically undefined:
    - oldest is zero (division by zero)
    - sign change between oldest and newest (negative base with fractional exponent → complex)

    Note: both-negative (continued losses) returns a valid float, but the sign is
    counter-intuitive — e.g. -2→-1 gives CAGR=-50% even though losses halved.
    Callers consuming this for LLM prompts should be aware of this interpretation.
    """
    if oldest == 0:
        return None
    ratio = newest / oldest
    if ratio <= 0:
        return None
    return ratio ** (1.0 / n_years) - 1


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
        structure_zone_detector: StructureZoneDetector | None = None,
        pattern_engine: PatternEngine | None = None,
        level_payload_composer: Callable | None = None,
        structure_presentation_adapter: Callable | None = None,
        playbook_engine=None,
    ):
        self.technical_tool = technical_tool
        self.news_tool = news_tool
        self.llm = llm
        self.fundamental_tool = fundamental_tool
        self.disclosure_tool = disclosure_tool
        self.flow_tool = flow_tool
        self.structure_zone_detector = structure_zone_detector or StructureZoneDetector()
        self.pattern_engine = pattern_engine or PatternEngine()
        self.level_payload_composer = level_payload_composer or compose_level_payload
        self.structure_presentation_adapter = (
            structure_presentation_adapter or build_structure_presentation
        )
        self.playbook_engine = playbook_engine

    async def run(self, ticker: str) -> dict:
        """Run deep dive analysis for a ticker.

        Returns:
            dict with keys:
                - ticker: str
                - technical: TechnicalResult
                - technical_summary: TechnicalSummaryOutput
                - decision_summary: AnalyzeDecisionSummary
                - factor_assessments: list[FactorAssessment]
                - scenarios: list[AnalyzeScenario]
                - news: list[NewsArticle]
                - news_analysis: NewsAnalysisOutput | None
                - fundamental: FundamentalSnapshot | None
                - fundamental_summary: FundamentalSummaryOutput | None
                - disclosure: list[DisclosureItem] | None (SEC 10-Q/8-K or OpenDART)
                - flow: InvestorFlow | None (외국인/기관 순매수 동향, 한국주식만)
                - integrated_analysis: IntegratedAnalysisOutput | None (종합 인사이트)
                - actionable_signal: ActionableSignalOutput | None (실행 가능한 투자 시그널)
        """
        tech_result = await self.technical_tool.execute(ticker, period="3y")
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
            for key, res in zip(optional_keys, opt_results, strict=True):
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

        # Generate actionable investment signal
        df = technical_data.raw_dataframe
        if df is None:
            raise ValueError("raw_dataframe required for pattern detection and charting")

        chart_patterns = self.pattern_engine.detect(df, technical_data.snapshot)
        lookback_high, lookback_low = get_fibonacci_base_points(df, technical_data.snapshot)
        price_levels = identify_key_levels(
            snapshot=technical_data.snapshot,
            pattern_results=chart_patterns,
            lookback_high=lookback_high,
            lookback_low=lookback_low,
        )
        zone_set = self.structure_zone_detector.detect(df, technical_data.snapshot)
        level_payload = self.level_payload_composer(
            zone_set,
            price_levels,
            atr=technical_data.snapshot.atr,
        )
        structure_levels = level_payload.structure_levels
        execution_levels = level_payload.execution_levels
        presented_structure = self.structure_presentation_adapter(
            structure_levels,
            execution_levels,
        )

        actionable_signal = await analyzer.generate_actionable_signal(
            ticker=ticker,
            technical_summary=f"{technical_summary.summary}\n\n{technical_summary.rationale}",
            chart_patterns=chart_patterns,
            price_levels=price_levels,
            structure_context=presented_structure.llm_context,
            structure_summary=presented_structure.structure_summary
            or level_payload.structure_summary,
            execution_summary=presented_structure.execution_summary
            or level_payload.execution_summary,
            llm=self.llm,
        )

        # PlaybookEngine evaluation (optional)
        playbook_verdict = None
        if self.playbook_engine is not None:
            try:
                holding = load_holdings().find(ticker)
                playbook_verdict = await self.playbook_engine.evaluate(
                    ticker=ticker,
                    technical_result=technical_data,
                    fundamental=fundamental_data,
                    flow=flow_data,
                    zone_set=zone_set,
                    holding=holding,
                )
            except Exception as e:
                logger.warning("PlaybookEngine evaluation failed for %s: %s", ticker, e)

        decision_bundle = build_analyze_decision_bundle(
            technical_data=technical_data,
            technical_summary=technical_summary,
            news_articles=news_articles,
            news_analysis=news_analysis,
            fundamental_summary=fundamental_summary,
            disclosure_items=disclosure_items,
            flow_data=flow_data,
            chart_patterns=chart_patterns,
            price_levels=price_levels,
        )
        decision_bundle = decision_bundle.model_copy(
            update={
                "summary": apply_playbook_veto(decision_bundle.summary, playbook_verdict),
            }
        )

        # Render technical chart
        chart_result = None
        try:
            chart_result = render_technical_chart(
                ticker=ticker,
                df=df,
                indicators=technical_data.snapshot.model_dump(),
                patterns=chart_patterns,
                price_levels={
                    "support_levels": price_levels.support_levels,
                    "resistance_levels": price_levels.resistance_levels,
                },
                out_dir="charts",
                window_days=200,  # MA200 표시 + 오래된 패턴도 보이도록
            )
        except Exception as e:
            logger.warning(f"Chart rendering failed for {ticker}: {e}")

        return {
            "ticker": ticker,
            "technical": technical_data,
            "technical_summary": technical_summary,
            "decision_summary": decision_bundle.summary,
            "factor_assessments": decision_bundle.factor_assessments,
            "scenarios": decision_bundle.scenarios,
            "chart_patterns": chart_patterns,
            "news": news_articles,
            "news_analysis": news_analysis,
            "fundamental": fundamental_data,
            "fundamental_summary": fundamental_summary,
            "disclosure": disclosure_items,
            "flow": flow_data,
            "integrated_analysis": integrated_analysis,
            "actionable_signal": actionable_signal,
            "structure_levels": structure_levels,
            "execution_levels": execution_levels,
            "presented_structure": presented_structure,
            "chart": chart_result,
            "playbook_verdict": playbook_verdict,
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
        if snapshot.perf_1m is not None:
            indicators["perf_1m"] = snapshot.perf_1m
        if snapshot.perf_3m is not None:
            indicators["perf_3m"] = snapshot.perf_3m
        if snapshot.perf_6m is not None:
            indicators["perf_6m"] = snapshot.perf_6m
        if snapshot.perf_1y is not None:
            indicators["perf_1y"] = snapshot.perf_1y

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
        available_metric_count = sum(
            1
            for field in _FUNDAMENTAL_SIGNAL_FIELDS
            if getattr(fundamental_data, field) is not None
        )
        if available_metric_count < 3:
            return FundamentalSummaryOutput(
                summary="핵심 재무 지표가 부족해 밸류 판단을 유보합니다.",
                strengths=[],
                weaknesses=["확인 가능한 재무 지표가 제한적임"],
                valuation_assessment="적정",
                confidence=0.2,
            )

        # Derive EPS growth metrics from quarterly/annual data
        eps_growth_quarterly: float | None = None
        if fundamental_data.quarterly_data:
            for q in fundamental_data.quarterly_data:
                if q.eps_yoy is not None:
                    eps_growth_quarterly = q.eps_yoy
                    break

        eps_cagr_annual: float | None = None
        if fundamental_data.annual_data and len(fundamental_data.annual_data) >= 2:
            ann = fundamental_data.annual_data
            newest = ann[0].eps
            oldest = ann[-1].eps
            n_years = len(ann) - 1
            if newest is not None and oldest is not None and n_years > 0:
                eps_cagr_annual = _compute_eps_cagr(newest, oldest, n_years)

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
            eps_growth_quarterly=eps_growth_quarterly,
            eps_cagr_annual=eps_cagr_annual,
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
