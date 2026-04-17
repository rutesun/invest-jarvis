"""Integration test for Plan 4: Advanced Technical Indicators + Component-based Scoring."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool


class MockProvider:
    """Mock provider for integration testing."""

    async def get_price_history(self, ticker: str, period: str):
        """Return realistic mock OHLCV data."""
        # Generate 250 days of realistic price data
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=250, freq="D")

        # Uptrend with some volatility
        trend = np.linspace(100, 130, 250)
        noise = np.random.randn(250) * 2
        close = trend + noise

        df = pd.DataFrame(
            {
                "Open": close - np.random.rand(250) * 0.5,
                "High": close + np.random.rand(250) * 2,
                "Low": close - np.random.rand(250) * 2,
                "Close": close,
                "Volume": np.random.randint(1000000, 5000000, 250),
            },
            index=dates,
        )

        return df


@pytest.mark.asyncio
async def test_plan4_complete_flow():
    """Test complete Plan 4 flow: indicators → components → scorer → tool."""
    # Step 1: Calculate indicators
    calculator = IndicatorCalculator()
    provider = MockProvider()
    df = await provider.get_price_history("TEST", "1y")
    df = calculator.calculate(df)

    # Verify all Plan 4 indicators are calculated
    assert "SMA_150" in df.columns
    assert "cRSI" in df.columns
    assert "cRSI_HighBand" in df.columns
    assert "cRSI_LowBand" in df.columns
    assert "Vol_SMA_20" in df.columns
    assert "Vol_SMA_50" in df.columns
    assert "Vol_SMA_120" in df.columns
    assert "Swing_High" in df.columns
    assert "Swing_Low" in df.columns
    assert "MACD_5_35_5" in df.columns

    # Step 2: Score with components
    scorer = TechnicalScorer()
    result = scorer.score(df, ticker="TEST")

    # Verify component structure
    assert result.components is not None
    assert "minervini" in result.components
    assert "velocity" in result.components
    assert "crsi" in result.components
    assert "volume" in result.components
    assert "patterns" in result.components

    # Verify each component has expected structure
    for name, comp in result.components.items():
        assert "score" in comp
        assert "signals" in comp
        assert "evidence" in comp
        assert "metrics" in comp
        assert isinstance(comp["score"], int)
        assert isinstance(comp["signals"], list)
        assert isinstance(comp["evidence"], list)
        assert isinstance(comp["metrics"], dict)

    # Verify total score is sum of components
    component_sum = sum(c["score"] for c in result.components.values())
    assert result.total_score == component_sum

    # Step 3: Test via TechnicalAnalysisTool
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)
    tool_result = await tool.execute("TEST")

    assert tool_result.success is True
    assert tool_result.data.ticker == "TEST"
    assert tool_result.data.components is not None
    assert tool_result.data.total_score is not None

    # Verify snapshot is populated
    assert tool_result.data.snapshot.price > 0
    assert tool_result.data.snapshot.sma_20 is not None
    assert tool_result.data.snapshot.sma_150 is not None
    assert tool_result.data.snapshot.crsi is not None


@pytest.mark.asyncio
async def test_plan4_minervini_stage2_detection():
    """Test Minervini Stage 2 detection with ideal conditions."""

    class Stage2Provider:
        """Provider that returns Stage 2 pattern data."""

        async def get_price_history(self, ticker: str, period: str):
            dates = pd.date_range(end=datetime.now(), periods=252, freq="D")
            # Perfect Stage 2: consistent uptrend, all MAs aligned
            close = 100 + np.arange(252) * 0.2
            df = pd.DataFrame(
                {
                    "Open": close - 0.1,
                    "High": close + 0.5,
                    "Low": close - 0.5,
                    "Close": close,
                    "Volume": [2000000] * 252,
                },
                index=dates,
            )
            return df

    provider = Stage2Provider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("STAGE2")

    # Should detect Stage 2 (score = 40)
    minervini = result.data.components["minervini"]
    assert minervini["score"] > 0
    assert any("Stage 2" in sig or "강세" in sig for sig in minervini["signals"])


@pytest.mark.asyncio
async def test_plan4_component_scoring_breakdown():
    """Test that each component contributes to total score."""
    provider = MockProvider()
    scorer = TechnicalScorer()
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("TEST")
    components = result.data.components

    # Each component should have metrics
    assert components["minervini"]["metrics"] != {}
    assert components["velocity"]["metrics"] != {}
    assert components["crsi"]["metrics"] != {}
    assert components["volume"]["metrics"] != {}

    # At least some components should have signals
    all_signals = []
    for comp in components.values():
        all_signals.extend(comp["signals"])
    assert len(all_signals) > 0

    # Total score should be non-zero for realistic data
    assert result.data.total_score != 0
