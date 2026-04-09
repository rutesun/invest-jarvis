# tests/tools/test_fundamental.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.fundamental import FundamentalTool, FundamentalSnapshot


@pytest.mark.asyncio
async def test_fundamental_tool_execute():
    mock_info = {
        "marketCap": 2800000000000,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "trailingPE": 28.5,
        "forwardPE": 25.0,
        "pegRatio": 1.8,
        "priceToBook": 45.0,
        "priceToSalesTrailing12Months": 7.5,
        "enterpriseToEbitda": 22.0,
        "trailingEps": 6.42,
        "ebitda": 130000000000,
        "grossMargins": 0.44,
        "operatingMargins": 0.30,
        "profitMargins": 0.25,
        "returnOnEquity": 1.60,
        "returnOnAssets": 0.28,
        "revenueGrowth": 0.08,
        "earningsGrowth": 0.12,
        "debtToEquity": 180.0,
        "currentRatio": 1.07,
        "quickRatio": 0.84,
        "freeCashflow": 100000000000,
        "operatingCashflow": 120000000000,
        "dividendYield": 0.005,
        "payoutRatio": 0.15,
        "sharesOutstanding": 15500000000,
        "floatShares": 15400000000,
    }

    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = MagicMock()
    mock_ticker.quarterly_financials.empty = True

    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = await tool.execute("AAPL")

    assert result.success is True
    snapshot = result.data
    assert isinstance(snapshot, FundamentalSnapshot)
    assert snapshot.pe_ratio == 28.5
    assert snapshot.sector == "Technology"
    assert snapshot.roe == 1.60
