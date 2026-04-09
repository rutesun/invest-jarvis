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
