from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.providers.kis import KISProvider


@pytest.fixture
def mock_token_response():
    return {
        "access_token": "test_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }


@pytest.fixture
def mock_quote_response():
    return {
        "output": {
            "stck_prpr": "70000",
            "prdy_vrss": "1000",
            "prdy_ctrt": "1.45",
            "acml_vol": "10000000",
        }
    }


@pytest.mark.asyncio
async def test_kis_get_access_token(mock_token_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_token_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test_key", app_secret="test_secret")
        token = await provider._get_access_token()

        assert token.access_token == "test_token"
        assert token.token_type == "Bearer"


@pytest.mark.asyncio
async def test_kis_get_quote(mock_token_response, mock_quote_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_quote_resp = MagicMock()
        mock_quote_resp.json.return_value = mock_quote_response
        mock_quote_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_quote_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test_key", app_secret="test_secret")
        quote = await provider.get_quote("005930")

        assert quote["ticker"] == "005930"
        assert quote["price"] == 70000.0


@pytest.mark.asyncio
async def test_kis_implements_base_provider():
    """Verify KISProvider implements BaseProvider interface."""
    from src.core.interfaces import BaseProvider

    provider = KISProvider(app_key="test", app_secret="test")
    assert isinstance(provider, BaseProvider)
