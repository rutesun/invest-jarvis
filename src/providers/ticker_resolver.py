# src/providers/ticker_resolver.py
import re
from typing import Optional
from pathlib import Path
import yaml
import yfinance as yf
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

        # Step 2: User cache lookup
        cached = self.user_cache.get(query)
        if cached:
            self.user_cache.update_usage(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=cached.ticker,
                display_name=cached.display_name,
                confidence="high",
                candidates=[],
                resolution_method="user_cache",
                source="user_cache"
            )

        # Step 3: Static mapping (Korean -> English)
        search_query = query
        if self._contains_korean(query) and query in self.static_mapping:
            search_query = self.static_mapping[query]

        # Step 4: yfinance Search API
        return await self._search_yfinance(query, search_query)

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

    def _contains_korean(self, text: str) -> bool:
        """Check if text contains Korean characters"""
        return bool(re.search(r'[가-힣]', text))

    async def _search_yfinance(self, original_query: str, search_query: str) -> TickerResolution:
        """Search for ticker using yfinance Search API"""
        # Check search cache first
        if search_query in self._search_cache:
            cached_result = self._search_cache[search_query]
            return TickerResolution(
                original_query=original_query,
                resolved_ticker=cached_result['ticker'],
                display_name=cached_result['name'],
                confidence=cached_result['confidence'],
                candidates=cached_result['candidates'],
                resolution_method=cached_result['resolution_method'],
                source="yfinance"
            )

        try:
            # Use yfinance search
            search_results = yf.Search(search_query, max_results=5)
            quotes = search_results.quotes

            if not quotes:
                raise TickerNotFoundError(f"Could not resolve: {original_query}")

            # Convert to CandidateTicker
            candidates = []
            for quote in quotes:
                symbol = quote.get('symbol', '')
                name = quote.get('longname') or quote.get('shortname', '')
                exchange = quote.get('exchange', '')
                quote_type = quote.get('quoteType', '')

                if symbol and name:
                    candidates.append(CandidateTicker(
                        symbol=symbol,
                        name=name,
                        exchange=exchange,
                        score=1.0,  # yfinance doesn't provide scores
                        quote_type=quote_type
                    ))

            if not candidates:
                raise TickerNotFoundError(f"Could not resolve: {original_query}")

            # Auto-select if only one result
            if len(candidates) == 1:
                result = candidates[0]
                confidence = "high"
                resolution_method = "yfinance_search_single"
            else:
                # Return first candidate with medium confidence
                result = candidates[0]
                confidence = "medium"
                resolution_method = "yfinance_search_multiple"

            # Cache the result
            self._search_cache[search_query] = {
                'ticker': result.symbol,
                'name': result.name,
                'confidence': confidence,
                'candidates': candidates,
                'resolution_method': resolution_method
            }

            # Save to user cache for future lookups
            self.user_cache.save(original_query, result.symbol, result.name)

            return TickerResolution(
                original_query=original_query,
                resolved_ticker=result.symbol,
                display_name=result.name,
                confidence=confidence,
                candidates=candidates,
                resolution_method=resolution_method,
                source="yfinance"
            )

        except Exception as e:
            if isinstance(e, TickerNotFoundError):
                raise
            raise TickerNotFoundError(f"Could not resolve: {original_query}") from e
