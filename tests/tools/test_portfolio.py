import pytest
from unittest.mock import AsyncMock
from src.tools.portfolio import PortfolioTool


@pytest.fixture
def mock_balance():
    return {
        "total_assets": 10000000,
        "cash": 3000000,
        "stock_value": 7000000,
        "positions": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "quantity": 100,
                "avg_price": 68000,
                "current_price": 70000,
                "profit_loss": 200000,
                "profit_loss_pct": 2.94,
            }
        ],
    }


@pytest.mark.asyncio
async def test_portfolio_tool_execute(mock_balance):
    mock_provider = AsyncMock()
    mock_provider.get_balance.return_value = mock_balance

    tool = PortfolioTool(provider=mock_provider)
    result = await tool.execute()

    assert result.success is True
    assert result.data["total_assets"] == 10000000
    assert len(result.data["positions"]) == 1
