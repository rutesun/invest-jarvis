# tests/tools/test_fundamental.py
import pandas as pd
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


@pytest.mark.asyncio
async def test_quarterly_data_parsing_with_data():
    mock_info = {
        "marketCap": 2800000000000,
        "freeCashflow": 100000000000,
    }

    q1 = pd.Period("2024Q1", freq="Q")
    q2 = pd.Period("2024Q2", freq="Q")
    q3 = pd.Period("2024Q3", freq="Q")
    q4 = pd.Period("2024Q4", freq="Q")

    mock_qf = pd.DataFrame(
        {
            q4: {"Total Revenue": 120000000000, "Net Income": 30000000000},
            q3: {"Total Revenue": 110000000000, "Net Income": 28000000000},
            q2: {"Total Revenue": 105000000000, "Net Income": 27000000000},
            q1: {"Total Revenue": 100000000000, "Net Income": 25000000000},
        }
    )

    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = mock_qf

    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = await tool.execute("AAPL")

    assert result.success is True
    snapshot = result.data
    assert snapshot.quarterly_data is not None
    assert len(snapshot.quarterly_data) == 4
    assert snapshot.quarterly_data[0].period == "2024-Q4"
    assert snapshot.quarterly_data[0].revenue == 120000000000
    assert snapshot.quarterly_data[0].earnings == 30000000000


@pytest.mark.asyncio
async def test_fcf_yield_calculation():
    mock_info = {
        "marketCap": 2000000000000,
        "freeCashflow": 100000000000,
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
    assert snapshot.fcf_yield == 0.05


@pytest.mark.asyncio
async def test_fcf_yield_when_no_data():
    mock_info = {"marketCap": None, "freeCashflow": None}

    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = MagicMock()
    mock_ticker.quarterly_financials.empty = True

    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = await tool.execute("AAPL")

    assert result.success is True
    snapshot = result.data
    assert snapshot.fcf_yield is None


@pytest.mark.asyncio
async def test_error_handling_for_quarterly_data():
    mock_info = {"marketCap": 2800000000000}

    mock_ticker = MagicMock()
    mock_ticker.info = mock_info
    mock_ticker.quarterly_financials = None

    with patch("yfinance.Ticker", return_value=mock_ticker):
        tool = FundamentalTool()
        result = await tool.execute("AAPL")

    assert result.success is True
    snapshot = result.data
    assert snapshot.quarterly_data is None


@pytest.mark.asyncio
async def test_error_handling_when_yfinance_fails():
    with patch("yfinance.Ticker", side_effect=Exception("Network error")):
        tool = FundamentalTool()
        result = await tool.execute("INVALID")

    assert result.success is False
    assert result.data is None
    assert "Network error" in result.error


def test_quarterly_data_model():
    """Verify QuarterlyData model fields."""
    from src.tools.fundamental import QuarterlyData

    data = QuarterlyData(
        period="2026-Q1",
        revenue=143756000000,
        earnings=36500000000,
        revenue_yoy=0.1565,
        revenue_qoq=0.4030,
        earnings_yoy=0.1830,
        earnings_qoq=0.3520,
    )
    assert data.period == "2026-Q1"
    assert data.revenue == 143756000000
    assert data.revenue_yoy == 0.1565
    assert data.revenue_qoq == 0.4030


def test_fundamental_snapshot_with_quarterly_data():
    """FundamentalSnapshot이 quarterly_data 필드를 지원하는지 검증"""
    from src.tools.fundamental import QuarterlyData

    quarterly = [
        QuarterlyData(period="2026-Q1", revenue=143756000000, earnings=36500000000),
        QuarterlyData(period="2025-Q4", revenue=102466000000, earnings=28300000000),
    ]
    snapshot = FundamentalSnapshot(
        market_cap=3828660000000,
        pe_ratio=33.0,
        quarterly_data=quarterly,
    )
    assert snapshot.quarterly_data is not None
    assert len(snapshot.quarterly_data) == 2
    assert snapshot.quarterly_data[0].period == "2026-Q1"
