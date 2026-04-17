import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.providers.ticker_models import TickerNotFoundError
from src.providers.ticker_resolver import TickerResolver


@pytest.mark.asyncio
async def test_resolve_direct_us_ticker():
    resolver = TickerResolver(openai_api_key="test-key")
    result = await resolver.resolve("AAPL")
    assert result.resolved_ticker == "AAPL"
    assert result.source == "direct_ticker"


@pytest.mark.asyncio
async def test_resolve_direct_korean_ticker():
    resolver = TickerResolver(openai_api_key="test-key")
    result = await resolver.resolve("005930.KS")
    assert result.resolved_ticker == "005930.KS"
    assert result.source == "direct_ticker"


@pytest.mark.asyncio
async def test_resolve_korean_ticker_normalization():
    resolver = TickerResolver(openai_api_key="test-key")
    result = await resolver.resolve("005930")
    assert result.resolved_ticker == "005930.KS"
    assert result.source == "direct_ticker"


@pytest.mark.asyncio
async def test_resolve_from_user_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.user_cache.save("애플", "AAPL", "Apple Inc.")

        result = await resolver.resolve("애플")

        assert result.resolved_ticker == "AAPL"
        assert result.display_name == "Apple Inc."
        assert result.source == "user_cache"


@pytest.mark.asyncio
async def test_resolve_cache_updates_usage():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.user_cache.save("Tesla", "TSLA", "Tesla, Inc.")
        initial_count = resolver.user_cache.get("Tesla").use_count

        await resolver.resolve("Tesla")

        assert resolver.user_cache.get("Tesla").use_count == initial_count + 1


@pytest.mark.asyncio
async def test_resolve_via_llm_agent():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.llm_agent.resolve = AsyncMock(
            return_value=("005930.KS", "Samsung Electronics Co., Ltd.")
        )

        result = await resolver.resolve("삼성전자")

        assert result.resolved_ticker == "005930.KS"
        assert result.display_name == "Samsung Electronics Co., Ltd."
        assert result.source == "llm_agent"


@pytest.mark.asyncio
async def test_resolve_llm_result_saved_to_cache():
    """LLM으로 해결된 결과가 캐시에 저장되어 다음 호출은 cache hit"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.llm_agent.resolve = AsyncMock(return_value=("035720.KQ", "Kakao Corp."))

        await resolver.resolve("카카오")
        # 두 번째 호출은 cache hit이어야 함
        resolver.llm_agent.resolve = AsyncMock(side_effect=Exception("should not be called"))
        result = await resolver.resolve("카카오")

        assert result.resolved_ticker == "035720.KQ"
        assert result.source == "user_cache"


@pytest.mark.asyncio
async def test_resolve_raises_when_llm_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path, openai_api_key="test-key")
        resolver.llm_agent.resolve = AsyncMock(side_effect=TickerNotFoundError("not found"))

        with pytest.raises(TickerNotFoundError):
            await resolver.resolve("존재하지않는회사xyz")
