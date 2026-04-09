# src/providers/ticker_resolver.py
import re
from typing import Optional
from pathlib import Path
import yaml
from src.providers.ticker_models import TickerResolution, CandidateTicker
from src.providers.ticker_cache import UserMappingCache


class TickerResolutionError(Exception):
    """Base exception for ticker resolution"""
    pass


class TickerNotFoundError(TickerResolutionError):
    """No ticker found for query"""
    pass


class TickerResolver:
    """Resolves user queries to ticker symbols"""

    def __init__(
        self,
        static_mapping_path: str = "config/ticker_names.yaml",
        user_cache_path: Optional[Path] = None
    ):
        self.static_mapping = self._load_static_mapping(static_mapping_path)
        self.user_cache = UserMappingCache(user_cache_path)
        self._search_cache = {}

    def _load_static_mapping(self, path: str) -> dict:
        """Load static Korean→English mapping"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                return data.get('korean_to_english', {})
        except FileNotFoundError:
            return {}

    async def resolve(self, query: str) -> TickerResolution:
        """
        Resolve user query to ticker symbol.

        Priority:
        1. Direct ticker detection
        2. User cache lookup
        3. Static mapping
        4. yfinance Search API
        """
        query = query.strip()

        # Step 1: Direct ticker detection
        if self._is_direct_ticker(query):
            normalized = self._normalize_ticker(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=normalized,
                display_name=normalized,
                confidence="high",
                candidates=[],
                resolution_method="direct_ticker",
                source="user_input"
            )

        # TODO: Step 2-4 in later tasks
        raise TickerNotFoundError(f"Could not resolve: {query}")

    def _is_direct_ticker(self, query: str) -> bool:
        """Check if query is already a valid ticker symbol"""
        patterns = [
            r'^[A-Z]{1,5}$',        # US stocks: AAPL, GOOGL
            r'^\d{6}\.KS$',         # Korean KOSPI: 005930.KS
            r'^\d{6}\.KQ$',         # Korean KOSDAQ: 123456.KQ
            r'^\d{6}$',             # Korean code without suffix
        ]
        return any(re.match(p, query) for p in patterns)

    def _normalize_ticker(self, query: str) -> str:
        """Normalize ticker format (add .KS for 6-digit codes)"""
        if re.match(r'^\d{6}$', query):
            return f"{query}.KS"
        return query
