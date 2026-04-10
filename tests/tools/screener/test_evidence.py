import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock
from src.tools.screener.evidence import EvidenceCollector
from src.tools.screener.models import UniverseStock, ScreenerEvidence


@pytest.fixture
def mock_kis():
    provider = AsyncMock()
    provider.get_investor_trend.return_value = [
        {"date": "20260409", "foreign_net": 100, "institution_net": 200, "total_net": 300},
        {"date": "20260408", "foreign_net": -50, "institution_net": 100, "total_net": 50},
    ]
    return provider


@pytest.fixture
def mock_yf():
    provider = AsyncMock()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.3
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


@pytest.mark.asyncio
async def test_collect_and_score(mock_kis, mock_yf):
    collector = EvidenceCollector(kis_provider=mock_kis, yf_provider=mock_yf)
    universe = [
        UniverseStock(
            ticker="005930",
            name="삼성전자",
            market="KOSPI",
            sources=["theme", "volume_rank"],
        ),
    ]
    results = await collector.collect_and_score(universe)

    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].stock.ticker == "005930"
    assert results[0].total_score >= 0


@pytest.mark.asyncio
async def test_score_tickers(mock_kis, mock_yf):
    collector = EvidenceCollector(kis_provider=mock_kis, yf_provider=mock_yf)
    results = await collector.score_tickers(["AAPL"])

    assert len(results) == 1
    assert results[0].stock.ticker == "AAPL"
    assert results[0].stock.market == "US"
    assert results[0].stock.sources == ["direct"]
