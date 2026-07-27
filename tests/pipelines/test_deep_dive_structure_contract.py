from datetime import datetime
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.core.models import ToolResult
from src.llm.models import IntegratedExplanationOutput, TechnicalSummaryOutput
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.news import NewsArticle
from src.tools.technical.models import IndicatorSnapshot, StrategyResult, TechnicalResult


@pytest.mark.asyncio
async def test_deep_dive_pipeline_passes_presented_structure_to_integrated_explanation():
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
        patch(
            "src.llm.analyzer.generate_integrated_explanation", new_callable=AsyncMock
        ) as mock_explanation,
    ):
        mock_tech.return_value = TechnicalSummaryOutput(
            summary="강세",
            key_insights=[],
            recommendation="매수",
            confidence=0.7,
            rationale="r",
        )
        mock_news.return_value = None
        mock_explanation.return_value = IntegratedExplanationOutput(
            decision_explanation="해설",
            rationale=[],
            risks=[],
            monitoring_points=[],
        )

        result = await DeepDivePipeline(
            technical_tool=technical_tool,
            news_tool=news_tool,
            llm=llm,
        ).run("AAPL")

    presented = result["presented_structure"]
    assert presented is not None
    assert "llm_context" in presented.model_dump()

    # presenter의 structure/execution 요약이 최종 해설 입력의 level_context에 도달한다
    explanation_input = mock_explanation.await_args.args[0]
    assert explanation_input.level_context["structure_summary"] == (
        presented.structure_summary or explanation_input.level_context["structure_summary"]
    )
    assert explanation_input.level_context["structure_levels"] == result[
        "structure_levels"
    ].model_dump(mode="json")
