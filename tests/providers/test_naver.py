import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.providers.naver import NaverProvider


@pytest.fixture
def mock_theme_list_response():
    return {
        "stocks": [
            {
                "name": "AI/반도체",
                "changeRate": "3.20",
                "themeCode": "TH001",
            },
            {
                "name": "2차전지",
                "changeRate": "2.10",
                "themeCode": "TH002",
            },
        ]
    }


@pytest.fixture
def mock_theme_stocks_response():
    return {
        "stocks": [
            {"itemcode": "005930", "itemname": "삼성전자", "sosok": "0"},
            {"itemcode": "000660", "itemname": "SK하이닉스", "sosok": "0"},
        ]
    }


@pytest.mark.asyncio
async def test_get_themes(mock_theme_list_response, mock_theme_stocks_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_response_list = MagicMock()
        mock_response_list.json.return_value = mock_theme_list_response
        mock_response_list.raise_for_status = MagicMock()

        mock_response_stocks = MagicMock()
        mock_response_stocks.json.return_value = mock_theme_stocks_response
        mock_response_stocks.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        mock_instance.get = AsyncMock(side_effect=[mock_response_list, mock_response_stocks, mock_response_stocks])
        mock_client.return_value.__aenter__.return_value = mock_instance

        provider = NaverProvider()
        themes = await provider.get_themes(top_n=2)

        assert len(themes) == 2
        assert themes[0]["name"] == "AI/반도체"
        assert themes[0]["change_rate"] == 3.20
        assert len(themes[0]["stocks"]) == 2
