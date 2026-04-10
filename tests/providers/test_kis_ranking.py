import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.providers.kis import KISProvider


@pytest.fixture
def mock_token_response():
    return {
        "access_token": "test_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }


@pytest.fixture
def mock_investor_ranking_response():
    return {
        "output": [
            {
                "hts_kor_isnm": "삼성전자",
                "mksc_shrn_iscd": "005930",
                "frgn_ntby_qty": "500000",
                "frgn_ntby_tr_pbmn": "35000000000",
            },
        ]
    }


@pytest.mark.asyncio
async def test_get_investor_ranking(mock_token_response, mock_investor_ranking_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = MagicMock()
        mock_ranking_resp.json.return_value = mock_investor_ranking_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_ranking_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_investor_ranking(investor_type="foreign", top_n=10)

        assert len(result) == 1
        assert result[0]["ticker"] == "005930"
        assert result[0]["name"] == "삼성전자"


@pytest.mark.asyncio
async def test_get_us_ranking_updown(mock_token_response):
    mock_us_response = {
        "output": {
            "body": [
                {
                    "symb": "NVDA",
                    "name": "NVIDIA Corp",
                    "rate": "5.20",
                    "last": "950.00",
                    "tvol": "50000000",
                },
            ]
        }
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = MagicMock()
        mock_ranking_resp.json.return_value = mock_us_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_ranking_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_us_ranking_updown(exchange="NAS", direction="up", top_n=10)

        assert len(result) == 1
        assert result[0]["ticker"] == "NVDA"


@pytest.mark.asyncio
async def test_get_us_ranking_volume(mock_token_response):
    mock_us_response = {
        "output": {
            "body": [
                {
                    "symb": "AAPL",
                    "name": "Apple Inc",
                    "last": "180.00",
                    "tvol": "75000000",
                },
            ]
        }
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = MagicMock()
        mock_ranking_resp.json.return_value = mock_us_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_ranking_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_us_ranking_volume(exchange="NAS", top_n=10)

        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["name"] == "Apple Inc"
        assert result[0]["volume"] == 75000000


@pytest.mark.asyncio
async def test_get_investor_trend(mock_token_response):
    mock_trend_response = {
        "output": [
            {
                "stck_bsop_date": "20260409",
                "frgn_ntby_qty": "100",
                "orgn_ntby_qty": "200",
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_trend_resp = MagicMock()
        mock_trend_resp.json.return_value = mock_trend_response
        mock_trend_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_trend_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_investor_trend(ticker="005930", days=10)

        assert len(result) == 1
        assert result[0]["date"] == "20260409"
        assert result[0]["foreign_net"] == 100
        assert result[0]["institution_net"] == 200
        assert result[0]["total_net"] == 300
