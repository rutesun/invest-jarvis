from datetime import datetime
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.core.models import ToolResult
from src.llm.models import TechnicalSummaryOutput
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.news import NewsArticle
from src.tools.technical.models import IndicatorSnapshot, StrategyResult, TechnicalResult


@pytest.mark.asyncio
async def test_deep_dive_pipeline_builds_presented_structure():
    """presented_structure 가 pipeline 결과에 채워지고 llm_context 필드를 갖는다."""
    technical_tool = AsyncMock()
    news_tool = AsyncMock()
    llm = AsyncMock()

    dates = pd.date_range(end=datetime.now(), periods=160, freq="D")
    mock_df = pd.DataFrame(
        {
            "Open": [100.0] * 160,
            "High": [103.0] * 160,
            "Low": [97.0] * 160,
            "Close": [100.0] * 160,
            "Volume": [1_000_000] * 160,
        },
        index=dates,
    )
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0, atr=3.0, sma_150=95.0)
    technical_tool.execute.return_value = ToolResult(
        success=True,
        data=TechnicalResult(
            ticker="AAPL",
            timestamp=datetime.now(),
            snapshot=snapshot,
            components={},
            total_score=75,
            raw_dataframe=mock_df,
            strategies=[
                StrategyResult(
                    name="trend",
                    status="강세",
                    confidence=70.0,
                    signals=["상승"],
                    evidence=["증거"],
                    metrics={},
                )
            ],
            indicators=snapshot,
            overall_assessment="매수",
            confidence_score=0.7,
            key_insights=[],
            warnings=[],
        ),
    )
    news_tool.execute.return_value = ToolResult(
        success=True,
        data=[NewsArticle(title="news", published="2026-05-01", summary="s", url="u")],
    )

    with (
        patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_tech,
        patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_news,
    ):
        mock_tech.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=[],
            recommendation="매수",
            confidence=0.7,
            rationale="r",
        )
        mock_news.return_value = None

        result = await DeepDivePipeline(
            technical_tool=technical_tool,
            news_tool=news_tool,
            llm=llm,
        ).run("AAPL")

    assert result["presented_structure"] is not None
    assert "llm_context" in result["presented_structure"].model_dump()
