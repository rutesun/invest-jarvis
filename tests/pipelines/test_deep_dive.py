import pytest
from unittest.mock import AsyncMock, patch
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.technical.models import (
    TechnicalResult,
    IndicatorSnapshot,
    StrategyResult,
)
from src.tools.news import NewsArticle
from src.llm.models import NewsAnalysisOutput, TechnicalSummaryOutput
from src.core.models import ToolResult
from datetime import datetime


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    tech_result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=IndicatorSnapshot(price=178.50, change_pct=2.5, rsi=58.0, sma_20=175.0, sma_50=170.0),
        components={
            "trend": {
                "signals": ["골든크로스"],
                "evidence": ["20일선 > 50일선"],
                "metrics": {"sma_20": 175.0},
                "score": 15,
            }
        },
        total_score=75,
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
    with patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech_summary:
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
                fundamental_tool=None,
            )

            result = await pipeline.run("AAPL")

            assert result["ticker"] == "AAPL"
            assert result["technical"] is not None
            assert result["technical_summary"].summary == "강세"
            assert result["news"] is not None
            assert result["news_analysis"].sentiment == "긍정"
            assert result["fundamental"] is None
            assert result["fundamental_summary"] is None


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
        fundamental_tool=None,
    )

    with pytest.raises(RuntimeError, match="News fetch failed"):
        await pipeline.run("AAPL")


@pytest.mark.asyncio
async def test_deep_dive_pipeline_empty_news(mock_technical_tool, mock_llm):
    """Test handling of empty news list."""
    mock_news_tool = AsyncMock()
    mock_news_tool.execute.return_value = ToolResult(success=True, data=[])

    with patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech_summary:
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
            fundamental_tool=None,
        )

        result = await pipeline.run("AAPL")

        assert result["ticker"] == "AAPL"
        assert result["news_analysis"] is None
