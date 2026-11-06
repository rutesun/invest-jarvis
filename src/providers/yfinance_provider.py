import asyncio
import logging
from collections.abc import Callable
from datetime import date, timedelta
from functools import partial

import pandas as pd
import yfinance as yf

from src.core.interfaces import BaseProvider
from src.providers.price_history_range import (
    RangeHistoryUnavailableError,
    RawHistory,
    unknown_history,
)


logger = logging.getLogger(__name__)


class YFinanceProvider(BaseProvider):
    """YFinance data provider for US stocks."""

    live_range_enabled = False
    range_evidence_status = "STUB_ONLY"

    def __init__(self, *, range_history_fetcher: Callable[..., pd.DataFrame] | None = None):
        self._range_history_fetcher = range_history_fetcher

    async def get_price_history_range(self, ticker: str, *, start: date, end: date) -> RawHistory:
        """Inclusive daily range using an explicit offline transport only.

        No default live fallback until captured raw range evidence is available.
        The injected callable follows ``Ticker.history`` keyword semantics.
        """
        if self._range_history_fetcher is None:
            raise RangeHistoryUnavailableError(
                "captured yfinance raw range evidence is unavailable"
            )
        if start > end:
            raise ValueError("range start must not follow end")
        loop = asyncio.get_event_loop()
        frame = await loop.run_in_executor(
            None,
            partial(
                self._range_history_fetcher,
                ticker,
                start=start,
                end=end + timedelta(days=1),
                interval="1d",
                auto_adjust=True,
            ),
        )
        return unknown_history(
            frame,
            provider="yfinance",
            adjustment_policy="YFINANCE_AUTO_ADJUST_TRUE_1D",
            start=start,
            end=end,
            reached_start=True,
        )

    async def get_quote(self, ticker: str) -> dict:
        """Get current quote for ticker."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._get_quote_sync, ticker))

    def _get_quote_sync(self, ticker: str) -> dict:
        """Synchronous quote fetching."""
        logger.debug("yfinance get_quote: %s", ticker)
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "name": info.get("shortName"),
            "quote_type": info.get("quoteType"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "volume": info.get("volume"),
        }

    async def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._get_history_sync, ticker, period))

    def _get_history_sync(self, ticker: str, period: str) -> pd.DataFrame:
        """Synchronous history fetching."""
        logger.debug("yfinance get_price_history: %s (period=%s)", ticker, period)
        t = yf.Ticker(ticker)
        df = t.history(period=period)
        logger.debug("yfinance returned %d rows for %s", len(df), ticker)
        return df
