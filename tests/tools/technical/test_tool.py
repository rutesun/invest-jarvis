import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, MagicMock
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.strategies.trend import TrendStrategy


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.5
    provider.get_price_history.return_value = pd.DataFrame({
        "Open": close - 0.5,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": [1000000] * 100,
    }, index=dates)
    return provider


@pytest.fixture
def registry():
    reg = StrategyRegistry()
    reg.register(TrendStrategy())
    return reg


@pytest.mark.asyncio
async def test_technical_tool_execute(mock_provider, registry):
    tool = TechnicalAnalysisTool(provider=mock_provider, registry=registry)
    result = await tool.execute("AAPL")

    assert result.success is True
    assert result.data is not None
    assert result.data.ticker == "AAPL"
    assert len(result.data.strategies) == 1


@pytest.mark.asyncio
async def test_technical_tool_has_indicators(mock_provider, registry):
    tool = TechnicalAnalysisTool(provider=mock_provider, registry=registry)
    result = await tool.execute("AAPL")

    assert result.data.indicators.price > 0
    assert result.data.indicators.sma_20 is not None
