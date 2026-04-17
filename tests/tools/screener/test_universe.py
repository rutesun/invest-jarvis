from unittest.mock import AsyncMock

import pytest

from src.tools.screener.universe import UniverseBuilder


@pytest.fixture
def mock_naver():
    provider = AsyncMock()
    provider.get_themes.return_value = [
        {
            "name": "AI/반도체",
            "change_rate": 3.2,
            "theme_id": "TH001",
            "stocks": [
                {"code": "005930", "name": "삼성전자", "market": "KOSPI"},
                {"code": "000660", "name": "SK하이닉스", "market": "KOSPI"},
            ],
        }
    ]
    provider.get_volume_ranking.return_value = [
        {
            "code": "005930",
            "name": "삼성전자",
            "market": "KOSPI",
            "price": 70000,
            "change_pct": 2.5,
            "volume": 5000000,
        },
    ]
    provider.get_rise_ranking.return_value = [
        {
            "code": "035420",
            "name": "NAVER",
            "market": "KOSPI",
            "price": 200000,
            "change_pct": 4.0,
            "volume": 1000000,
        },
    ]
    return provider


@pytest.fixture
def mock_kis():
    provider = AsyncMock()
    provider.get_investor_ranking.return_value = [
        {
            "ticker": "005930",
            "name": "삼성전자",
            "net_buy_volume": 500000,
            "net_buy_amount": 35000000000,
        },
    ]
    provider.get_us_ranking_updown.return_value = [
        {
            "ticker": "NVDA",
            "name": "NVIDIA",
            "change_pct": 5.0,
            "price": 950,
            "volume": 50000000,
            "exchange": "NAS",
        },
    ]
    provider.get_us_ranking_volume.return_value = []
    return provider


@pytest.mark.asyncio
async def test_build_kr_universe(mock_naver, mock_kis):
    builder = UniverseBuilder(
        naver_provider=mock_naver, kis_provider=mock_kis, yf_provider=AsyncMock()
    )
    universe = await builder.build(market="kr")

    # 005930 should appear from theme + volume + kis
    samsung = next((s for s in universe if s.ticker == "005930"), None)
    assert samsung is not None
    assert "theme" in samsung.sources
    assert "volume_rank" in samsung.sources
    assert "kis_rank" in samsung.sources
    assert samsung.theme == "AI/반도체"

    # NAVER from rise_rank only
    naver = next((s for s in universe if s.ticker == "035420"), None)
    assert naver is not None
    assert naver.sources == ["rise_rank"]


@pytest.mark.asyncio
async def test_build_us_universe(mock_naver, mock_kis):
    builder = UniverseBuilder(
        naver_provider=mock_naver, kis_provider=mock_kis, yf_provider=AsyncMock()
    )
    universe = await builder.build(market="us")

    nvda = next((s for s in universe if s.ticker == "NVDA"), None)
    assert nvda is not None
    assert nvda.market == "NAS"


@pytest.mark.asyncio
async def test_build_all_universe(mock_naver, mock_kis):
    builder = UniverseBuilder(
        naver_provider=mock_naver, kis_provider=mock_kis, yf_provider=AsyncMock()
    )
    universe = await builder.build(market="all")

    tickers = [s.ticker for s in universe]
    assert "005930" in tickers
    assert "NVDA" in tickers
