# tests/providers/test_ticker_resolver.py
import tempfile
from pathlib import Path

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


@pytest.mark.asyncio
async def test_resolve_from_user_cache():
    """Test resolution from user cache"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path)

        # Pre-populate cache
        resolver.user_cache.save('애플', 'AAPL', 'Apple Inc.')

        result = await resolver.resolve('애플')

        assert result.resolved_ticker == 'AAPL'
        assert result.display_name == 'Apple Inc.'
        assert result.resolution_method == 'user_cache'
        assert result.confidence == 'high'


@pytest.mark.asyncio
async def test_resolve_cache_updates_usage():
    """Test cache usage is updated on hit"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path)

        resolver.user_cache.save('Tesla', 'TSLA', 'Tesla, Inc.')
        initial_count = resolver.user_cache.get('Tesla').use_count

        await resolver.resolve('Tesla')

        updated_count = resolver.user_cache.get('Tesla').use_count
        assert updated_count == initial_count + 1
