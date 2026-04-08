import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.providers.yfinance_provider import YFinanceProvider


@pytest.mark.asyncio
async def test_get_quote():
    provider = YFinanceProvider()

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "currentPrice": 178.50,
        "previousClose": 175.00,
        "shortName": "Apple Inc.",
    }

    with patch("yfinance.Ticker", return_value=mock_ticker):
        quote = await provider.get_quote("AAPL")

    assert quote["price"] == 178.50
    assert quote["previous_close"] == 175.00
    assert quote["name"] == "Apple Inc."


@pytest.mark.asyncio
async def test_get_price_history():
    provider = YFinanceProvider()

    mock_df = pd.DataFrame({
        "Open": [170.0, 172.0],
        "High": [175.0, 178.0],
        "Low": [169.0, 171.0],
        "Close": [174.0, 177.0],
        "Volume": [1000000, 1200000],
    })

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_df

    with patch("yfinance.Ticker", return_value=mock_ticker):
        df = await provider.get_price_history("AAPL", "1y")

    assert len(df) == 2
    assert "Close" in df.columns
    mock_ticker.history.assert_called_once_with(period="1y")
