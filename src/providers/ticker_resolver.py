import os
import re
import logging
from typing import Optional
from pathlib import Path

from src.providers.ticker_models import TickerResolution, TickerNotFoundError, TickerResolutionError
from src.providers.ticker_cache import UserMappingCache
from src.providers.llm_ticker_agent import LLMTickerAgent

logger = logging.getLogger(__name__)


class TickerResolver:
    """사용자 쿼리를 티커 심볼로 해결한다."""

    def __init__(
        self,
        user_cache_path: Optional[Path] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.user_cache = UserMappingCache(user_cache_path)
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.llm_agent = LLMTickerAgent(api_key=api_key)

    async def resolve(self, query: str) -> TickerResolution:
        """
        사용자 쿼리를 티커 심볼로 해결한다.

        우선순위:
        1. Direct ticker 감지
        2. 유저 캐시 조회
        3. LLM Agent (GPT-4o + DuckDuckGo)
        """
        query = query.strip()

        if self._is_direct_ticker(query):
            normalized = self._normalize_ticker(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=normalized,
                display_name=normalized,
                source="direct_ticker",
            )

        cached = self.user_cache.get(query)
        if cached:
            if not cached.ticker:
                logger.debug("Cache hit for '%s' but ticker is None — evicting", query)
                self.user_cache.evict(query)
            else:
                self.user_cache.update_usage(query)
                logger.debug("Cache hit: %s → %s", query, cached.ticker)
                return TickerResolution(
                    original_query=query,
                    resolved_ticker=cached.ticker,
                    display_name=cached.display_name,
                    source="user_cache",
                )

        logger.debug("Calling LLM agent for: %s", query)
        ticker, display_name = await self.llm_agent.resolve(query)
        self.user_cache.save(query, ticker, display_name)
        return TickerResolution(
            original_query=query,
            resolved_ticker=ticker,
            display_name=display_name,
            source="llm_agent",
        )

    def _is_direct_ticker(self, query: str) -> bool:
        patterns = [
            r'^[A-Z]{1,5}$',
            r'^\d{6}\.KS$',
            r'^\d{6}\.KQ$',
            r'^\d{6}$',
        ]
        return any(re.match(p, query) for p in patterns)

    def _normalize_ticker(self, query: str) -> str:
        if re.match(r'^\d{6}$', query):
            return f"{query}.KS"
        return query
