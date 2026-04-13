# tests/pipelines/report_stages/test_ingest.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipelines.report_stages.ingest import IngestStage
from src.llm.daily_report_models import IngestResult


@pytest.fixture
def mock_macro_tool():
    tool = AsyncMock()
    tool.execute.return_value = MagicMock(
        success=True,
        data=MagicMock(
            vix=18.2, vix_change=1.3, fear_greed=62, fear_greed_label="Greed",
            wti=78.5, wti_change=1.2, us_10y=4.32, us_2y=3.87,
            yield_spread=0.45, dxy=104.2, dxy_change=-0.3,
        ),
    )
    return tool


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock()
    tool.execute.return_value = MagicMock(
        success=True,
        data=[
            MagicMock(title="SPY rises", summary="S&P 500 up 1%", url="http://example.com"),
        ],
    )
    return tool


@pytest.fixture
def mock_kis_provider():
    provider = AsyncMock()
    provider.get_investor_ranking.return_value = [
        {"ticker": "005930", "name": "삼성전자", "net_buy_volume": 500, "net_buy_amount": 30000},
    ]
    provider.get_us_ranking_updown.return_value = [
        {"ticker": "NVDA", "name": "NVIDIA", "change_pct": 5.8, "price": 950, "volume": 100000, "exchange": "NAS"},
    ]
    provider.get_us_ranking_volume.return_value = [
        {"ticker": "NVDA", "name": "NVIDIA", "price": 950, "volume": 200000, "exchange": "NAS"},
    ]
    return provider


@pytest.fixture
def mock_telegram_loader():
    loader = MagicMock()
    loader.load.return_value = [
        {"id": 1, "channel": "ch1", "text": "엔비디아 실적 호조", "timestamp": "2026-04-13T09:00:00"},
    ]
    return loader


@pytest.mark.asyncio
async def test_ingest_stage_returns_ingest_result(
    mock_macro_tool, mock_news_tool, mock_kis_provider, mock_telegram_loader
):
    stage = IngestStage(
        macro_tool=mock_macro_tool,
        news_tool=mock_news_tool,
        kis_provider=mock_kis_provider,
        telegram_loader=mock_telegram_loader,
    )
    result = await stage.run()

    assert isinstance(result, IngestResult)
    assert len(result.telegram_messages) == 1
    assert result.macro_snapshot["vix"] == 18.2
    assert len(result.market_news) >= 1
    assert len(result.kr_flow) >= 1
    assert len(result.momentum) >= 1


@pytest.mark.asyncio
async def test_ingest_stage_handles_kis_failure(
    mock_macro_tool, mock_news_tool, mock_telegram_loader
):
    mock_kis = AsyncMock()
    mock_kis.get_investor_ranking.side_effect = Exception("KIS API down")
    mock_kis.get_us_ranking_updown.side_effect = Exception("KIS API down")
    mock_kis.get_us_ranking_volume.side_effect = Exception("KIS API down")

    stage = IngestStage(
        macro_tool=mock_macro_tool,
        news_tool=mock_news_tool,
        kis_provider=mock_kis,
        telegram_loader=mock_telegram_loader,
    )
    result = await stage.run()

    assert isinstance(result, IngestResult)
    assert result.kr_flow == []
    assert result.momentum == []
