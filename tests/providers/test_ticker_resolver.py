# tests/providers/test_ticker_resolver.py
import pytest
from src.providers.ticker_resolver import TickerResolver


@pytest.mark.asyncio
async def test_resolve_direct_us_ticker():
    """Test direct US ticker detection"""
    resolver = TickerResolver()

    result = await resolver.resolve("AAPL")

    assert result.original_query == "AAPL"
    assert result.resolved_ticker == "AAPL"
    assert result.confidence == "high"
    assert result.resolution_method == "direct_ticker"
    assert len(result.candidates) == 0


@pytest.mark.asyncio
async def test_resolve_direct_korean_ticker():
    """Test direct Korean ticker detection"""
    resolver = TickerResolver()

    result = await resolver.resolve("005930.KS")

    assert result.resolved_ticker == "005930.KS"
    assert result.resolution_method == "direct_ticker"
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_resolve_korean_ticker_normalization():
    """Test 6-digit code auto-adds .KS suffix"""
    resolver = TickerResolver()

    result = await resolver.resolve("005930")

    assert result.resolved_ticker == "005930.KS"
    assert result.resolution_method == "direct_ticker"
