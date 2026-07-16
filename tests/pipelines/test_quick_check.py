from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.core.models import ToolResult
from src.pipelines.quick_check import QuickCheckPipeline
from src.tools.technical.models import (
    IndicatorSnapshot,
    ScoreHistoryPoint,
    StrategyResult,
    TechnicalResult,
    TechnicalVerdict,
)


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    indicators = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_20=175.0,
        sma_50=170.0,
        rsi=58.3,
    )
    strategy = StrategyResult(
        name="trend",
        status="강세",
        confidence=75.0,
        signals=["골든크로스"],
        evidence=["20일선 > 50일선"],
        metrics={"sma_20": 175.0},
    )
    tech_result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=indicators,
        indicators=indicators,
        components={},
        total_score=75,
        strategies=[strategy],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["골든크로스"],
        warnings=[],
    )
    tool.execute.return_value = ToolResult(success=True, data=tech_result)
    return tool


@pytest.mark.asyncio
async def test_quick_check_run(mock_technical_tool):
    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")

    assert result["ticker"] == "AAPL"
    assert result["price"] == 178.50
    assert result["assessment"] == "매수"
    mock_technical_tool.execute.assert_called_once_with("AAPL")


@pytest.mark.asyncio
async def test_quick_check_format_output(mock_technical_tool):
    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")
    output = pipeline.format_output(result)

    assert "AAPL" in output
    assert "178.50" in output
    assert "매수" in output


@pytest.mark.asyncio
async def test_quick_check_run_includes_verdict_and_score_history(mock_technical_tool):
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
            date="2026-07-10",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]

    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")

    assert result["adjusted_score"] == 62
    assert result["technical_verdict"]["action"] == "hold"
    assert result["score_history"][0]["adjusted_score"] == 62


@pytest.mark.asyncio
async def test_quick_check_format_output_shows_verdict_reasons_and_history(
    mock_technical_tool,
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
            date="2026-07-10",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]

    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    output = pipeline.format_output(await pipeline.run("AAPL"))

    assert "Adjusted Score" in output
    assert "상승 추세 유지" in output
    assert "최근 5거래일" in output
    assert "2026-07-10" in output
