from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.core.models import ToolResult
from src.llm.models import NewsAnalysisOutput, TechnicalSummaryOutput
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.news import NewsArticle
from src.tools.technical.models import (
    IndicatorSnapshot,
    StrategyResult,
    TechnicalResult,
)


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    snapshot = IndicatorSnapshot(price=178.50, change_pct=2.5)
    tech_result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=75,
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
    with patch(
        "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
    ) as mock_tech_summary:
        with patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news_analysis:
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

            pipeline = DeepDivePipeline(
                technical_tool=mock_technical_tool,
                news_tool=mock_news_tool,
                llm=mock_llm,
            )

            result = await pipeline.run("AAPL")

            assert result["ticker"] == "AAPL"
            assert result["technical"] is not None
            assert result["technical_summary"].summary == "강세"
            assert result["news"] is not None
            assert result["news_analysis"].sentiment == "긍정"


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

    with patch(
        "src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock
    ) as mock_tech_summary:
        mock_tech_summary.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=["골든크로스"],
            recommendation="매수",
            confidence=0.75,
            rationale="좋음",
        )

        pipeline = DeepDivePipeline(
            technical_tool=mock_technical_tool,
            news_tool=mock_news_tool,
            llm=mock_llm,
        )

        result = await pipeline.run("AAPL")

        assert result["ticker"] == "AAPL"
        assert result["news_analysis"] is None  # No news analysis when news is empty
