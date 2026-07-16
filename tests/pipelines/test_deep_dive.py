from datetime import datetime
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.core.models import ToolResult
from src.llm.models import ActionableSignalOutput, NewsAnalysisOutput, TechnicalSummaryOutput
from src.pipelines.analyze_decision import (
    AnalyzeDecisionBundle,
    AnalyzeDecisionSummary,
    AnalyzeScenario,
    FactorAssessment,
)
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.fundamental import FundamentalSnapshot
from src.tools.news import NewsArticle
from src.tools.technical.models import (
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


@pytest.mark.asyncio
async def test_deep_dive_pipeline_success(mock_technical_tool, mock_news_tool, mock_llm):
    """Test successful deep dive analysis."""
    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
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
        mock_signal.return_value = ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=8,
            headline="매수. 지금. 이유: 골든크로스",
            primary_reason="골든크로스 발생",
            supporting_reasons=["상승 추세"],
            risks=["변동성"],
            confidence=0.75,
        )
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
        )

        result = await pipeline.run("AAPL")

        mock_technical_tool.execute.assert_awaited_once_with("AAPL", period="3y")
        assert result["ticker"] == "AAPL"
        assert result["technical"] is not None
        assert result["technical_summary"].summary == "강세"
        assert result["news"] is not None
        assert result["news_analysis"].sentiment == "긍정"
        assert result["actionable_signal"] is not None
        assert result["actionable_signal"].action == "매수"
        assert result["actionable_signal"].timing == "지금"
        assert result["structure_levels"].support_zones[0].lower_bound == 170.0
        assert result["execution_levels"][0].description == "피봇 S1"
        assert result["presented_structure"].headline == "핵심 지지 존 우위"
        assert result["decision_summary"].leader in {"technical", "혼합", "판단 보류"}
        assert result["factor_assessments"]
        assert result["scenarios"]
        assert result["chart_patterns"]
        assert "170.00~172.00" in mock_signal.await_args.kwargs["structure_context"]


@pytest.mark.asyncio
async def test_deep_dive_pipeline_returns_decision_bundle(
    mock_technical_tool, mock_news_tool, mock_llm
):
    with (
        patch(
            "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
        ) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
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
        mock_signal.return_value = ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=8,
            headline="매수",
            primary_reason="골든크로스",
            supporting_reasons=[],
            risks=[],
            confidence=0.75,
        )
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
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_signal.return_value = ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=8,
            headline="매수. 지금.",
            primary_reason="골든크로스",
            supporting_reasons=[],
            risks=[],
            confidence=0.75,
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

        assert result["ticker"] == "AAPL"
        assert result["news_analysis"] is None  # No news analysis when news is empty
        assert result["actionable_signal"] is not None
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
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
    ):
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )
        mock_signal.return_value = ActionableSignalOutput(
            action="관망",
            timing="보류",
            signal_strength=5,
            headline="관망",
            primary_reason="근거 부족",
            supporting_reasons=[],
            risks=[],
            confidence=0.45,
        )

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
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
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
        mock_signal.return_value = ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=8,
            headline="매수",
            primary_reason="골든크로스",
            supporting_reasons=[],
            risks=[],
            confidence=0.75,
        )
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
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
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
        mock_signal.return_value = ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=8,
            headline="매수",
            primary_reason="골든크로스",
            supporting_reasons=[],
            risks=[],
            confidence=0.75,
        )

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

    with (
        patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech_summary,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis,
        patch("src.llm.analyzer.generate_actionable_signal", new_callable=AsyncMock) as mock_signal,
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
        mock_signal.return_value = ActionableSignalOutput(
            action="관망",
            timing="보류",
            signal_strength=5,
            headline="관망",
            primary_reason="단기 과열",
            supporting_reasons=["상승 추세 유지"],
            risks=["추격 매수 리스크"],
            confidence=0.7,
        )
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
