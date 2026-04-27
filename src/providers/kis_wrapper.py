"""KIS Provider wrapper for yfinance-compatible interface."""

import pandas as pd

from src.core.interfaces import BaseProvider
from src.providers.kis import KISProvider


class KISProviderWrapper(BaseProvider):
    """Wrapper around KIS Provider to normalize ticker format.

    KIS API uses raw ticker codes (e.g., "448900"),
    while yfinance uses suffixed tickers (e.g., "448900.KS").
    This wrapper strips the suffix before calling KIS API.
    """

    def __init__(self, kis_provider: KISProvider):
        self.kis_provider = kis_provider

    async def get_quote(self, ticker: str) -> dict:
        """Get current quote.

        Args:
            ticker: Ticker with suffix (e.g., "448900.KS")

        Returns:
            Quote data dict
        """
        # Strip .KS/.KQ suffix for KIS API
        raw_ticker = ticker.split(".")[0]

        # Call KIS API
        return await self.kis_provider.get_quote(raw_ticker)

    async def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data.

        Args:
            ticker: Ticker with suffix (e.g., "448900.KS")
            period: Time period (e.g., "1y", "6mo")

        Returns:
            DataFrame with OHLC data
        """
        # Strip .KS/.KQ suffix for KIS API
        raw_ticker = ticker.split(".")[0]

        # Call KIS API
        df = await self.kis_provider.get_price_history(raw_ticker, period)

        return df
