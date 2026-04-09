import pytest
from unittest.mock import AsyncMock, MagicMock
import pandas as pd
import numpy as np
from src.pipelines.quick_check import QuickCheckPipeline
from src.tools.technical.models import TechnicalResult, IndicatorSnapshot, StrategyResult
from src.core.models import ToolResult
from datetime import datetime


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
