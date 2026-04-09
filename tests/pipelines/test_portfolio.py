import pytest
from unittest.mock import AsyncMock
from src.pipelines.portfolio import PortfolioPipeline


@pytest.fixture
def mock_portfolio_tool():
    tool = AsyncMock()
    tool.execute.return_value.success = True
    tool.execute.return_value.data = {
        "total_assets": 10000000,
        "positions": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "quantity": 100,
                "current_price": 70000,
                "profit_loss_pct": 2.94,
            }
        ],
    }
    return tool


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    from src.tools.technical.models import IndicatorSnapshot, StrategyResult, TechnicalResult
    from datetime import datetime

    snapshot = IndicatorSnapshot(price=70000, change_pct=1.5)
    components = {
        "minervini": {"score": 20, "signals": ["골든크로스"], "evidence": ["20일선 > 50일선"], "metrics": {}},
        "velocity": {"score": 10, "signals": [], "evidence": [], "metrics": {}},
        "crsi": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
        "volume": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
        "patterns": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
    }
    tech_result = TechnicalResult(
        ticker="005930",
        timestamp=datetime.now(),
        snapshot=snapshot,
        components=components,
        total_score=45,
        indicators=snapshot,
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
    tool.execute.return_value.success = True
    tool.execute.return_value.data = tech_result
    return tool


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock()
    tool.execute.return_value.success = True
    tool.execute.return_value.data = [
        {"title": "삼성전자 실적 발표", "published": "2024-01-01", "summary": "좋은 실적"}
    ]
    return tool


@pytest.mark.asyncio
async def test_portfolio_pipeline_run(
    mock_portfolio_tool, mock_technical_tool, mock_news_tool
):
    pipeline = PortfolioPipeline(
        portfolio_tool=mock_portfolio_tool,
        technical_tool=mock_technical_tool,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run()

    assert result["success"] is True
    assert result["total_assets"] == 10000000
    assert len(result["holdings"]) == 1
    assert result["holdings"][0]["ticker"] == "005930"
    assert "technical" in result["holdings"][0]
