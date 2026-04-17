import pandas as pd
import pytest

from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool


class MockProvider:
    """Mock provider for testing."""

    async def get_price_history(self, ticker: str, period: str):
        """Return mock OHLCV data."""
        data = []
        for i in range(250):
            data.append(
                {
                    "Open": 100 + i * 0.1,
                    "High": 101 + i * 0.1,
                    "Low": 99 + i * 0.1,
                    "Close": 100.5 + i * 0.1,
                    "Volume": 1000000 + i * 1000,
                }
            )
        return pd.DataFrame(data)


@pytest.mark.asyncio
async def test_technical_tool_with_scorer():
    """Test TechnicalAnalysisTool uses TechnicalScorer."""
    provider = MockProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("AAPL")

    assert result.success is True
    assert result.data is not None
    assert result.data.ticker == "AAPL"
    assert result.data.total_score is not None
    assert isinstance(result.data.components, dict)
    assert len(result.data.components) > 0


@pytest.mark.asyncio
async def test_technical_tool_components_present():
    """Test all components are analyzed."""
    provider = MockProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("AAPL")

    expected_components = ["minervini", "velocity", "crsi", "volume", "patterns"]
    for component in expected_components:
        assert component in result.data.components


@pytest.mark.asyncio
async def test_technical_tool_snapshot():
    """Test snapshot is included."""
    provider = MockProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("AAPL")

    assert result.data.snapshot is not None
    assert result.data.snapshot.price > 0


@pytest.mark.asyncio
async def test_technical_tool_no_data():
    """Test tool handles no data gracefully."""

    class EmptyProvider:
        async def get_price_history(self, ticker: str, period: str):
            return pd.DataFrame()

    provider = EmptyProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("INVALID")

    assert result.success is False
    assert result.error is not None
