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


@pytest.mark.asyncio
async def test_negative_score_propagation():
    """Test negative scores (Egg pattern) propagate to total_score correctly."""

    class EggProvider:
        """Provider that creates Egg pattern (high volume down-day)."""

        async def get_price_history(self, ticker: str, period: str):
            data = []
            # 29 days with normal volume and down days
            for _ in range(29):
                data.append(
                    {
                        "Open": 101,
                        "High": 102,
                        "Low": 99,
                        "Close": 100,  # Down day (close < open)
                        "Volume": 1000000,
                    }
                )
            # Last day: down day with 1.6M volume (160% avg) → Egg pattern (-15 pts)
            data.append(
                {
                    "Open": 101,
                    "High": 102,
                    "Low": 99,
                    "Close": 100,
                    "Volume": 1600000,  # 1.6x avg > 150% threshold
                }
            )
            return pd.DataFrame(data)

    provider = EggProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("EGG")

    assert result.success is True
    assert result.data is not None

    # Egg pattern should be detected in volume component
    assert "volume" in result.data.components
    volume_comp = result.data.components["volume"]
    assert any("Egg" in sig or "추가 하락" in sig for sig in volume_comp["signals"]), (
        f"Expected Egg signal, got: {volume_comp['signals']}"
    )
    assert volume_comp["score"] == -15, f"Expected Egg score -15, got: {volume_comp['score']}"

    # Negative score should propagate to total_score
    # total_score = sum of all component scores
    # Egg contributes -15, so total_score should reflect this
    assert result.data.total_score < 0, (
        f"Expected negative total_score (Egg -15), got: {result.data.total_score}"
    )
