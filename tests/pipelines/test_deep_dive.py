from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.core.models import ToolResult
from src.llm.models import (
    IntegratedExplanationOutput,
    NewsAnalysisOutput,
    TechnicalSummaryOutput,
)
from src.pipelines.analyze_decision import (
    AnalyzeDecisionBundle,
    AnalyzeDecisionSummary,
    AnalyzeScenario,
    FactorAssessment,
)
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.disclosure import DisclosureItem
from src.tools.flow import InvestorFlow, InvestorFlowEntry
from src.tools.fundamental import FundamentalSnapshot
from src.tools.macro import TickerMacroSnapshot
from src.tools.news import NewsArticle
from src.tools.technical.models import (
    AggregationTraceEntry,
    ExecutionLevelView,
    IndicatorSnapshot,
    InvalidationLevelView,
    LevelPayload,
    ScoreHistoryPoint,
    StrategyResult,
    StructureLevelsPayloadV2,
    StructureLevelView,
    TechnicalResult,
    TechnicalVerdict,
)


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    snapshot = IndicatorSnapshot(price=178.50, change_pct=2.5)

    # Create mock OHLC dataframe (150 days for pattern detection)
    dates = pd.date_range(end=datetime.now(), periods=150, freq="D")
    mock_df = pd.DataFrame(
        {
            "Open": [170.0] * 150,
            "High": [180.0] * 150,
            "Low": [165.0] * 150,
            "Close": [175.0] * 150,
            "Volume": [1_000_000] * 150,
        },
        index=dates,
    )

    tech_result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=75,
        raw_dataframe=mock_df,
        strategies=[
            StrategyResult(
                name="trend",
                status="강세",
                confidence=75.0,
                signals=["골든크로스"],
                evidence=["20일선 > 50일선"],
                metrics={},
            )
        ],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["상승 추세"],
        warnings=[],
    )
    tool.execute.return_value = ToolResult(success=True, data=tech_result)
    return tool


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock()
    news = [
        NewsArticle(
            title="Apple 신제품 출시",
            published="2024-01-01",
            summary="애플이 새로운 제품을 출시했습니다",
            url="https://example.com/news/1",
        )
    ]
    tool.execute.return_value = ToolResult(success=True, data=news)
    return tool


@pytest.fixture
def mock_llm():
    """Mock LangChain chat model."""
    llm = AsyncMock()
    return llm


@pytest.fixture
def mock_macro_tool():
    tool = AsyncMock()
    snapshot = TickerMacroSnapshot(
        timestamp=datetime(2026, 7, 22),
        vix=18.5,
        vix_change=1.2,
        fear_greed=55,
        fear_greed_label="Neutral",
        wti=68.4,
        wti_change=-0.7,
        us_10y=4.25,
        us_2y=3.85,
        yield_spread=0.4,
        dxy=101.2,
        dxy_change=0.3,
    )
    tool.execute.return_value = ToolResult(success=True, data=snapshot)
    return tool


@pytest.mark.asyncio
async def test_deep_dive_pipeline_success(
    mock_technical_tool, mock_news_tool, mock_llm, mock_macro_tool
):
    """Test successful deep dive analysis."""
    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
        patch("src.pipelines.deep_dive.StructureZoneDetector") as mock_zone_detector_cls,
        patch("src.pipelines.deep_dive.compose_level_payload") as mock_compose_levels,
    ):
        # Mock LLM outputs
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=["신제품"],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_signal.return_value = _explanation_output()
        mock_zone_detector = mock_zone_detector_cls.return_value
        mock_zone_detector.detect.return_value = object()
        mock_compose_levels.return_value = LevelPayload(
            structure_levels=StructureLevelsPayloadV2(
                summary_label="support_zone",
                headline="핵심 지지 존 우위",
                why="최근 지지 반응 우세",
                active_box=None,
                support_zones=[
                    StructureLevelView(
                        lower_bound=170.0,
                        upper_bound=172.0,
                        mid_price=171.0,
                        strength="core",
                        reasons=["반복 지지"],
                        touch_count=3,
                        last_touch_date="2026-05-01",
                        total_score=10.0,
                    )
                ],
                resistance_zones=[
                    StructureLevelView(
                        lower_bound=180.0,
                        upper_bound=182.0,
                        mid_price=181.0,
                        strength="secondary",
                        reasons=["매물대"],
                        touch_count=2,
                        last_touch_date="2026-05-02",
                        total_score=8.0,
                    )
                ],
                former_levels=[],
                invalidation=InvalidationLevelView(
                    label="170.00~172.00 하향 이탈",
                    lower_bound=170.0,
                    upper_bound=172.0,
                    reference="반복 지지",
                    reasons=["반복 지지"],
                ),
                patterns_reference=[],
            ),
            execution_levels=[
                ExecutionLevelView(
                    type="pivot_s1",
                    description="피봇 S1",
                    price=172.0,
                    distance_pct=-3.6,
                )
            ],
            structure_summary="핵심 지지 존 우위 | 지지 1개, 저항 1개",
            execution_summary="피봇 S1 $172.00 (-3.6%)",
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
            macro_tool=mock_macro_tool,
        )

        result = await pipeline.run("AAPL")

        mock_technical_tool.execute.assert_awaited_once_with("AAPL")
        assert result["ticker"] == "AAPL"
        assert result["technical"] is not None
        assert result["technical_summary"].summary == "강세"
        assert result["technical_summary"].recommendation == "매수"
        assert result["technical"].total_score == 75
        assert result["news"] is not None
        assert result["news_analysis"].sentiment == "긍정"
        mock_macro_tool.execute.assert_awaited_once_with()
        assert result["macro"] is mock_macro_tool.execute.return_value.data
        assert result["integrated_explanation"] is not None
        assert result["integrated_explanation"].decision_explanation == "해설"
        assert result["structure_levels"].support_zones[0].lower_bound == 170.0
        assert result["execution_levels"][0].description == "피봇 S1"
        assert result["presented_structure"].headline == "핵심 지지 존 우위"
        assert result["decision_summary"].leader in {"technical", "혼합", "판단 보류"}
        assert result["factor_assessments"]
        assert result["scenarios"]
        assert result["chart_patterns"]
        explanation_input = mock_signal.await_args.args[0]
        assert (
            explanation_input.level_context["structure_levels"]["support_zones"][0]["lower_bound"]
            == 170.0
        )


@pytest.mark.asyncio
async def test_deep_dive_continues_when_macro_fails(
    mock_technical_tool,
    mock_news_tool,
    mock_llm,
):
    macro_tool = AsyncMock()
    macro_tool.execute.return_value = ToolResult(success=False, data=None, error="macro down")

    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=["신제품"],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_signal.return_value = _explanation_output()
        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
            macro_tool=macro_tool,
        )
        result = await pipeline.run("AAPL")

    assert result["macro"] is None
    assert result["technical"] is not None


@pytest.mark.asyncio
async def test_deep_dive_pipeline_returns_decision_bundle(
    mock_technical_tool, mock_news_tool, mock_llm
):
    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
        patch("src.pipelines.deep_dive.build_analyze_decision_bundle") as mock_bundle,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=["신제품"],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_signal.return_value = _explanation_output()
        mock_bundle.return_value = AnalyzeDecisionBundle(
            summary=AnalyzeDecisionSummary(
                leader="technical",
                core_variables=["가격 모멘텀"],
                action="관망",
                timing="조정_대기",
                action_sentence="눌림 확인 후 접근",
            ),
            factor_assessments=[
                FactorAssessment(
                    factor_type="technical",
                    role="주도",
                    freshness_score=4,
                    magnitude_score=4,
                    actionability_score=3,
                    total_score=11,
                    summary="가격 모멘텀",
                    role_reason="추세가 현재 액션과 직접 연결됨",
                    evidence=["technical total_score=75"],
                )
            ],
            scenarios=[
                AnalyzeScenario(
                    name="기본 시나리오",
                    trigger_price_levels=["20일선 유지"],
                    confirming_factors=["거래량 유지"],
                    invalidation_conditions=["20일선 종가 이탈"],
                    expected_path="눌림 후 재상승",
                    recommended_action="조정 구간 접근",
                )
            ],
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

        mock_bundle.assert_called_once()
        bundle_kwargs = mock_bundle.call_args.kwargs

        assert result["decision_summary"].leader == "technical"
        assert result["factor_assessments"][0].role == "주도"
        assert result["scenarios"][0].name == "기본 시나리오"
        assert bundle_kwargs["technical_summary"].summary == "강세"
        assert bundle_kwargs["news_analysis"].summary == "긍정적"


@pytest.mark.asyncio
async def test_deep_dive_uses_rule_verdict_recommendation_for_final_explanation(
    mock_technical_tool,
    mock_news_tool,
    mock_llm,
):
    tech = mock_technical_tool.execute.return_value.data
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=None,
    )
    disclosure_tool = AsyncMock()
    disclosure_tool.execute.return_value = ToolResult(
        success=True,
        data=[
            DisclosureItem(
                form_type="8-K",
                date="2026-07-16",
                description="테스트 공시",
                url="https://example.com",
            )
        ],
    )

    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
        patch("src.pipelines.deep_dive.StructureZoneDetector") as mock_zone_detector_cls,
        patch("src.pipelines.deep_dive.compose_level_payload") as mock_compose_levels,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="LLM은 매수라고 해석함",
            key_insights=["강력 매수"],
            recommendation="매수",
            confidence=0.9,
            rationale="LLM 판단",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="중립",
            confidence=0.5,
            key_themes=[],
            summary="뉴스 제한적",
            impact_assessment="영향 제한",
        )
        mock_signal.return_value = _explanation_output()
        mock_zone_detector_cls.return_value.detect.return_value = object()
        mock_compose_levels.return_value = LevelPayload(
            structure_levels=StructureLevelsPayloadV2(
                summary_label="no_clear_structure",
                headline="명확한 구조 없음",
                why="테스트 기본값",
            ),
            execution_levels=[],
            structure_summary="명확한 구조 없음",
            execution_summary="실행 레벨 없음",
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
            disclosure_tool=disclosure_tool,
        )
        result = await pipeline.run("AAPL")

    # rule verdict가 technical_summary.recommendation과 최종 해설 입력에 반영된다
    assert result["technical_summary"].recommendation == "중립"
    explanation_input = mock_signal.call_args.args[0]
    assert explanation_input.technical_context["technical_verdict"]["action"] == "hold"


@pytest.mark.asyncio
async def test_deep_dive_pipeline_technical_failure(mock_news_tool, mock_llm):
    """Test handling of technical analysis failure."""
    mock_technical_tool = AsyncMock()
    mock_technical_tool.execute.return_value = ToolResult(
        success=False, data=None, error="API error"
    )

    pipeline = DeepDivePipeline(
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
        llm=mock_llm,
    )

    with pytest.raises(RuntimeError, match="Technical analysis failed"):
        await pipeline.run("AAPL")


@pytest.mark.asyncio
async def test_deep_dive_pipeline_news_failure(mock_technical_tool, mock_llm):
    """Test handling of news fetch failure."""
    mock_news_tool = AsyncMock()
    mock_news_tool.execute.return_value = ToolResult(
        success=False, data=None, error="News API error"
    )

    pipeline = DeepDivePipeline(
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
        llm=mock_llm,
    )

    with pytest.raises(RuntimeError, match="News fetch failed"):
        await pipeline.run("AAPL")


@pytest.mark.asyncio
async def test_deep_dive_pipeline_empty_news(mock_technical_tool, mock_llm):
    """Test handling of empty news list."""
    mock_news_tool = AsyncMock()
    mock_news_tool.execute.return_value = ToolResult(success=True, data=[])

    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_signal.return_value = _explanation_output()

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

        assert result["ticker"] == "AAPL"
        assert result["news_analysis"] is None  # No news analysis when news is empty
        assert result["integrated_explanation"] is not None
        assert result["decision_summary"].leader == "판단 보류"
        assert result["decision_summary"].action == "관망"
        assert result["decision_summary"].timing == "보류"
        assert result["decision_summary"].defer_reason is not None


@pytest.mark.asyncio
async def test_deep_dive_pipeline_uses_defer_state_when_news_and_flow_are_missing(
    mock_technical_tool, mock_llm
):
    empty_news_tool = AsyncMock()
    empty_news_tool.execute.return_value = ToolResult(success=True, data=[])

    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_signal.return_value = _explanation_output()

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=empty_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

        assert result["decision_summary"].leader == "판단 보류"
        assert result["decision_summary"].action == "관망"
        assert result["decision_summary"].timing == "보류"
        assert result["decision_summary"].defer_reason is not None


@pytest.mark.asyncio
async def test_generate_fundamental_summary_uses_rule_based_fallback_when_metrics_are_sparse(
    mock_technical_tool, mock_news_tool, mock_llm
):
    pipeline = DeepDivePipeline(
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
        llm=mock_llm,
    )

    with patch(
        "src.pipelines.deep_dive.generate_fundamental_summary", new_callable=AsyncMock
    ) as mock_generate:
        summary = await pipeline._generate_fundamental_summary(
            "033100.KQ",
            FundamentalSnapshot(),
        )

    mock_generate.assert_not_awaited()
    assert summary.summary == "핵심 재무 지표가 부족해 밸류 판단을 유보합니다."
    assert summary.valuation_assessment == "적정"
    assert summary.confidence == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_deep_dive_pipeline_with_playbook_engine_returns_verdict(
    mock_technical_tool, mock_news_tool, mock_llm
):
    """PlaybookEngine이 주입되면 run() 결과에 playbook_verdict 키가 존재해야 한다."""
    from unittest.mock import MagicMock

    from src.tools.playbook.models import (
        CanslimResult,
        ElementVerdict,
        GateResult,
        MarketRegimeResult,
        PlaybookVerdict,
        RelativeStrengthResult,
    )

    # PlaybookVerdict mock
    mock_verdict = PlaybookVerdict(
        ticker="AAPL",
        holding=False,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=5.0,
            outperform_6m=10.0,
            rp_slope_4w=0.5,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=CanslimResult(
            c=ElementVerdict(met=True),
            a=ElementVerdict(met=True),
            n=ElementVerdict(met=None),
            s=ElementVerdict(met=True),
            l=ElementVerdict(met=True),
            i=ElementVerdict(met=None),
            m=ElementVerdict(met=True),
        ),
        gate=GateResult(
            passed=True,
            checklist=[],
            quality_grade="B",
            veto_reason=None,
        ),
        position_plan=None,
        exit_verdict=None,
        headline="AAPL: 매수 적격 (grade=B) — 비율 모드",
    )

    mock_engine = AsyncMock()
    mock_engine.evaluate.return_value = mock_verdict

    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
        patch("src.pipelines.deep_dive.load_holdings") as mock_load_holdings,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=[],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=["신제품"],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_signal.return_value = _explanation_output()
        mock_holdings = MagicMock()
        mock_holdings.find.return_value = None  # 미보유
        mock_load_holdings.return_value = mock_holdings

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
            playbook_engine=mock_engine,
        )

        result = await pipeline.run("AAPL")

    assert "playbook_verdict" in result
    assert result["playbook_verdict"] is mock_verdict
    mock_engine.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_deep_dive_pipeline_without_playbook_engine_returns_none_verdict(
    mock_technical_tool, mock_news_tool, mock_llm
):
    """PlaybookEngine이 없으면 playbook_verdict는 None이어야 한다 (기존 동작 보존)."""
    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=[],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=[],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_signal.return_value = _explanation_output()

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

    assert result.get("playbook_verdict") is None


@pytest.mark.asyncio
async def test_deep_dive_passes_verdict_and_score_history_to_technical_summary(
    mock_technical_tool,
    mock_news_tool,
    mock_llm,
):
    tech = mock_technical_tool.execute.return_value.data
    tech.adjusted_score = 62
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=170.0,
        score_trend_summary="최근 5거래일 adjusted score는 70에서 62로 악화",
    )
    tech.score_history = [
        ScoreHistoryPoint(
            date="2026-07-16",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]
    tech.score_history_warning = "score history 일부 기간 부족"
    tech.aggregation_trace = [
        AggregationTraceEntry(
            rule="overextended_penalty",
            before=70,
            after=62,
            reason="단기 과열",
        )
    ]

    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_signal,
        patch("src.pipelines.deep_dive.StructureZoneDetector") as mock_zone_detector_cls,
        patch("src.pipelines.deep_dive.compose_level_payload") as mock_compose_levels,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["상승 추세 유지"],
            recommendation="중립",
            confidence=0.7,
            rationale="rule output 설명",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="중립",
            confidence=0.5,
            key_themes=[],
            summary="뉴스 제한적",
            impact_assessment="영향 제한",
        )
        mock_signal.return_value = _explanation_output()
        mock_zone_detector_cls.return_value.detect.return_value = object()
        mock_compose_levels.return_value = LevelPayload(
            structure_levels=StructureLevelsPayloadV2(
                summary_label="no_clear_structure",
                headline="명확한 구조 없음",
                why="테스트 기본값",
            ),
            execution_levels=[],
            structure_summary="명확한 구조 없음",
            execution_summary="실행 레벨 없음",
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )
        await pipeline.run("AAPL")

    input_data = mock_tech_summary.call_args.args[0]
    assert input_data.technical_verdict["action"] == "hold"
    assert input_data.score_history[0]["adjusted_score"] == 62
    assert input_data.score_history_warning == "score history 일부 기간 부족"
    assert input_data.aggregation_trace[0]["rule"] == "overextended_penalty"


def _explanation_output() -> IntegratedExplanationOutput:
    return IntegratedExplanationOutput(
        decision_explanation="해설",
        rationale=["근거"],
        risks=["리스크"],
        monitoring_points=["모니터링"],
    )


@pytest.mark.asyncio
async def test_deep_dive_builds_all_source_integrated_explanation(
    mock_technical_tool, mock_news_tool, mock_llm, mock_macro_tool
):
    """모든 분석 소스와 veto가 적용된 고정 decision이 단일 최종 해설 입력으로 전달돼야 한다."""
    from src.tools.playbook.models import (
        GateCheck,
        GateResult,
        MarketRegimeResult,
        PlaybookVerdict,
        RelativeStrengthResult,
    )

    tech = mock_technical_tool.execute.return_value.data
    tech.component_raw_total = 75
    tech.adjusted_score = 62
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=None,
    )

    disclosure = DisclosureItem(
        form_type="8-K",
        date="2026-07-16",
        description="테스트 공시",
        url="https://example.com",
    )
    disclosure_tool = AsyncMock()
    disclosure_tool.execute.return_value = ToolResult(success=True, data=[disclosure])

    flow = InvestorFlow(
        code="005930",
        entries=[
            InvestorFlowEntry(date="2026-07-16", foreign_net=1000, institution_net=-500),
        ],
    )
    flow_tool = AsyncMock()
    flow_tool.execute.return_value = ToolResult(success=True, data=flow)

    verdict = PlaybookVerdict(
        ticker="005930.KS",
        holding=False,
        market_regime=MarketRegimeResult(regime="하락", allow_new_buy=False, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=-2.0,
            outperform_6m=-5.0,
            rp_slope_4w=-0.3,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=None,
        gate=GateResult(
            passed=False,
            checklist=[
                GateCheck(name="시장환경(A)", required=True, met=False, reason="SPY 하락추세")
            ],
            quality_grade=None,
            veto_reason="시장 환경 불량: 하락 국면",
        ),
        position_plan=None,
        exit_verdict=None,
        headline="005930.KS: 매수 거부",
    )
    playbook_engine = AsyncMock()
    playbook_engine.evaluate.return_value = verdict

    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_explanation,
        patch("src.pipelines.deep_dive.StructureZoneDetector") as mock_zone_detector_cls,
        patch("src.pipelines.deep_dive.compose_level_payload") as mock_compose_levels,
        patch("src.pipelines.deep_dive.load_holdings") as mock_load_holdings,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=["신제품"],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_explanation.return_value = _explanation_output()
        mock_zone_detector_cls.return_value.detect.return_value = object()
        mock_compose_levels.return_value = LevelPayload(
            structure_levels=StructureLevelsPayloadV2(
                summary_label="support_zone",
                headline="핵심 지지 존 우위",
                why="근거",
            ),
            execution_levels=[],
            structure_summary="핵심 지지 존 우위 | 지지 1개",
            execution_summary="실행 레벨 없음",
        )
        mock_holdings = MagicMock()
        mock_holdings.find.return_value = None
        mock_load_holdings.return_value = mock_holdings

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
            disclosure_tool=disclosure_tool,
            flow_tool=flow_tool,
            macro_tool=mock_macro_tool,
            playbook_engine=playbook_engine,
        )
        result = await pipeline.run("005930.KS")

    mock_explanation.assert_awaited_once()
    captured = mock_explanation.call_args.args[0]
    decision = result["decision_summary"]

    # 규칙이 확정한 (veto 적용된) decision을 그대로 넘긴다
    assert decision.veto_applied is True
    assert decision.action == "관망"
    assert captured.fixed_action == decision.action
    assert captured.fixed_timing == decision.timing
    assert captured.fixed_action_sentence == decision.action_sentence

    # technical_context 계약
    assert set(captured.technical_context) == {
        "components",
        "component_raw_total",
        "adjusted_score",
        "technical_verdict",
        "score_history",
        "aggregation_trace",
    }
    assert captured.technical_context["adjusted_score"] == 62
    assert captured.technical_context["component_raw_total"] == 75
    assert captured.technical_context["technical_verdict"]["action"] == "hold"

    # 소스별 매핑
    assert captured.news_analysis == mock_news_analysis.return_value.model_dump(mode="json")
    assert captured.fundamental_summary is None
    assert captured.disclosure_items == [disclosure.model_dump(mode="json")]
    assert captured.flow_context["code"] == "005930"
    assert captured.flow_context["foreign"]["direction_1d"] == flow.foreign_direction_1d
    assert captured.flow_context["institution"]["net_1d"] == flow.institution_net_1d
    assert captured.flow_context["entries"][0]["foreign_net"] == 1000
    assert captured.macro_context == mock_macro_tool.execute.return_value.data.model_dump(
        mode="json"
    )
    assert captured.playbook_context["veto_applied"] is True
    assert captured.playbook_context["gate"] == verdict.gate.model_dump(mode="json")
    assert captured.factor_assessments
    assert captured.scenarios

    # veto 이후 재구성된 시나리오만 노출/직렬화된다
    assert result["scenarios"][0].recommended_action == decision.action_sentence
    assert captured.scenarios[0]["recommended_action"] == decision.action_sentence

    # level_context는 presenter 요약을 담는다
    presented = result["presented_structure"]
    expected_structure_summary = (
        presented.structure_summary or mock_compose_levels.return_value.structure_summary
    )
    assert captured.level_context["structure_summary"] == expected_structure_summary

    # 경쟁하던 액션 경로는 제거된다
    assert "actionable_signal" not in result
    assert "integrated_analysis" not in result
    assert result["integrated_explanation"].decision_explanation == "해설"


@pytest.mark.asyncio
async def test_deep_dive_integrated_explanation_handles_absent_sources(
    mock_technical_tool, mock_news_tool, mock_llm
):
    """공시·수급·Macro·Playbook·펀더멘털이 없어도 최종 해설은 한 번 호출된다."""
    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_explanation,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_news_analysis.return_value = NewsAnalysisOutput(
            sentiment="긍정",
            confidence=0.85,
            key_themes=["신제품"],
            summary="긍정적",
            impact_assessment="좋음",
        )
        mock_explanation.return_value = _explanation_output()

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )
        result = await pipeline.run("AAPL")

    mock_explanation.assert_awaited_once()
    captured = mock_explanation.call_args.args[0]
    assert captured.fundamental_summary is None
    assert captured.disclosure_items == []
    assert captured.flow_context is None
    assert captured.macro_context is None
    assert captured.playbook_context is None
    assert captured.news_analysis == mock_news_analysis.return_value.model_dump(mode="json")
    assert "actionable_signal" not in result
    assert result["integrated_explanation"] is not None
