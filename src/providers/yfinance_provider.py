import asyncio
from functools import partial
import pandas as pd
import yfinance as yf
from src.core.interfaces import BaseProvider


class YFinanceProvider(BaseProvider):
    """YFinance data provider for US stocks."""

    async def get_quote(self, ticker: str) -> dict:
        """Get current quote for ticker."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._get_quote_sync, ticker))

    def _get_quote_sync(self, ticker: str) -> dict:
        """Synchronous quote fetching."""
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "name": info.get("shortName"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "volume": info.get("volume"),
        }

    async def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._get_history_sync, ticker, period)
        )

    def _get_history_sync(self, ticker: str, period: str) -> pd.DataFrame:
        """Synchronous history fetching."""
        t = yf.Ticker(ticker)
        return t.history(period=period)
