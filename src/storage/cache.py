import time
from typing import Any, Callable, Awaitable, Optional


class MemoryCache:
    """TTL-based in-memory cache."""

    def __init__(self):
        self._cache: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None

        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None

        return value

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache with TTL in seconds."""
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl: int = 300,
    ) -> Any:
        """Get from cache or fetch and cache."""
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await fetcher()
        await self.set(key, value, ttl)
        return value

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
