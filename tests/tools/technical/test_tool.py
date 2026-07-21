from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.5
    provider.get_price_history.return_value = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1000000] * 100,
        },
        index=dates,
    )
    return provider


@pytest.fixture
def scorer():
    return TechnicalScorer()


@pytest.mark.asyncio
async def test_technical_tool_execute(mock_provider, scorer):
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)
    result = await tool.execute("AAPL")

    assert result.success is True
    assert result.data is not None
    assert result.data.ticker == "AAPL"
    assert result.data.components is not None
    assert len(result.data.components) > 0


@pytest.mark.asyncio
async def test_technical_tool_uses_canonical_three_year_period_by_default(
    mock_provider, scorer
):
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)

    await tool.execute("AAPL")

    mock_provider.get_price_history.assert_awaited_once_with("AAPL", "3y")


@pytest.mark.asyncio
async def test_technical_tool_has_indicators(mock_provider, scorer):
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)
    result = await tool.execute("AAPL")

    # Support both old (indicators) and new (snapshot) fields
    snapshot = result.data.indicators or result.data.snapshot
    assert snapshot.price > 0
    assert snapshot.sma_20 is not None
