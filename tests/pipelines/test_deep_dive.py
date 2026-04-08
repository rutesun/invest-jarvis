import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.news import NewsTool, NewsArticle
from src.tools.technical.models import TechnicalResult, IndicatorSnapshot, StrategyResult
from src.llm.client import LLMClient
from src.llm.models import TechnicalSummaryOutput, NewsAnalysisOutput
from src.core.models import ToolResult


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock(spec=TechnicalAnalysisTool)
    tech_result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        indicators=IndicatorSnapshot(
            price=178.50,
            change_pct=2.5,
            sma_20=175.0,
            sma_50=170.0,
            rsi=58.3,
        ),
        strategies=[
            StrategyResult(
                name="trend",
                status="강세",
                confidence=75.0,
                signals=["골든크로스"],
                evidence=["20일선 > 50일선"],
                metrics={"sma_20": 175.0},
            )
        ],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["골든크로스 발생"],
        warnings=[],
    )
    tool.execute.return_value = ToolResult(success=True, data=tech_result)
    return tool


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock(spec=NewsTool)
    articles = [
        NewsArticle(
            title="Apple releases new product",
            published="2024-01-01T10:00:00",
            summary="Apple announced a new product line",
            url="https://example.com/1",
        ),
        NewsArticle(
            title="Apple stock rises on earnings",
            published="2024-01-02T10:00:00",
            summary="Stock price increased after strong earnings",
            url="https://example.com/2",
        ),
    ]
    tool.execute.return_value = ToolResult(success=True, data=articles)
    return tool


@pytest.fixture
def mock_llm_client():
    client = AsyncMock(spec=LLMClient)
    client.generate_technical_summary.return_value = TechnicalSummaryOutput(
        summary="AAPL은 강한 상승 추세입니다.",
        key_insights=["골든크로스 발생", "RSI 중립권"],
        recommendation="매수",
        confidence=0.75,
        rationale="이동평균선 정배열과 모멘텀 지표 긍정적",
    )
    client.analyze_news.return_value = NewsAnalysisOutput(
        sentiment="긍정",
        confidence=0.85,
        key_themes=["신제품 출시", "실적 개선"],
        summary="애플이 새로운 제품을 출시하고 실적이 개선되었습니다.",
        impact_assessment="단기 긍정적 영향 예상",
    )
    return client


@pytest.mark.asyncio
async def test_deep_dive_pipeline_success(
    mock_technical_tool, mock_news_tool, mock_llm_client
):
    pipeline = DeepDivePipeline(
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
        llm_client=mock_llm_client,
    )

    result = await pipeline.run(ticker="AAPL")

    assert result["ticker"] == "AAPL"
    assert "technical" in result
    assert "technical_summary" in result
    assert "news" in result
    assert "news_analysis" in result

    assert result["technical"].ticker == "AAPL"
    assert result["technical_summary"].recommendation == "매수"
    assert result["news_analysis"].sentiment == "긍정"

    mock_technical_tool.execute.assert_called_once_with("AAPL")
    mock_news_tool.execute.assert_called_once_with("AAPL", limit=10)
    mock_llm_client.generate_technical_summary.assert_called_once()
    mock_llm_client.analyze_news.assert_called_once()


@pytest.mark.asyncio
async def test_deep_dive_pipeline_technical_failure(
    mock_technical_tool, mock_news_tool, mock_llm_client
):
    mock_technical_tool.execute.return_value = ToolResult(
        success=False, data=None, error="Failed to fetch data"
    )

    pipeline = DeepDivePipeline(
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
        llm_client=mock_llm_client,
    )

    with pytest.raises(RuntimeError, match="Technical analysis failed"):
        await pipeline.run(ticker="AAPL")


@pytest.mark.asyncio
async def test_deep_dive_pipeline_news_failure(
    mock_technical_tool, mock_news_tool, mock_llm_client
):
    mock_news_tool.execute.return_value = ToolResult(
        success=False, data=None, error="Failed to fetch news"
    )

    pipeline = DeepDivePipeline(
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
        llm_client=mock_llm_client,
    )

    with pytest.raises(RuntimeError, match="News fetch failed"):
        await pipeline.run(ticker="AAPL")


@pytest.mark.asyncio
async def test_deep_dive_pipeline_empty_news(
    mock_technical_tool, mock_news_tool, mock_llm_client
):
    mock_news_tool.execute.return_value = ToolResult(success=True, data=[])

    pipeline = DeepDivePipeline(
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
        llm_client=mock_llm_client,
    )

    result = await pipeline.run(ticker="AAPL")

    assert result["ticker"] == "AAPL"
    assert result["news"] == []
    assert result["news_analysis"] is None
    mock_llm_client.analyze_news.assert_not_called()
