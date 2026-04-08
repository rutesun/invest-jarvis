import pytest
import asyncio
from src.storage.cache import MemoryCache


@pytest.mark.asyncio
async def test_cache_set_and_get():
    cache = MemoryCache()
    await cache.set("key1", {"value": 123}, ttl=60)
    result = await cache.get("key1")
    assert result == {"value": 123}


@pytest.mark.asyncio
async def test_cache_miss():
    cache = MemoryCache()
    result = await cache.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_cache_expiry():
    cache = MemoryCache()
    await cache.set("key1", "value", ttl=0)
    await asyncio.sleep(0.01)
    result = await cache.get("key1")
    assert result is None


@pytest.mark.asyncio
async def test_cache_get_or_fetch():
    cache = MemoryCache()
    call_count = 0

    async def fetcher():
        nonlocal call_count
        call_count += 1
        return {"data": "fetched"}

    result1 = await cache.get_or_fetch("key", fetcher, ttl=60)
    result2 = await cache.get_or_fetch("key", fetcher, ttl=60)

    assert result1 == {"data": "fetched"}
    assert result2 == {"data": "fetched"}
    assert call_count == 1
