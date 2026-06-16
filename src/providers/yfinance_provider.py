import asyncio
import logging
from datetime import time as dtime
from functools import partial

import pandas as pd
import yfinance as yf

from src.core.interfaces import BaseProvider


logger = logging.getLogger(__name__)

_REGULAR_OPEN = "09:30"
_REGULAR_CLOSE = "16:00"
_SESSION_COMPLETE_AFTER = dtime(15, 55)  # 정규장 종가 근처까지 도달해야 '완성' 세션


def backfill_daily_from_intraday(daily_df: pd.DataFrame, intraday_df: pd.DataFrame) -> pd.DataFrame:
    """일봉의 NaN 완성봉을 1분봉 정규장 집계로 백필 (순수 함수, I/O 없음).

    야후 일봉 피드가 최근 완성 세션을 NaN으로 비우는 경우가 있어, 같은 구간의
    1분봉(정규장 09:30–16:00 ET)을 일봉 OHLCV로 집계해 채운다. 세션이 종가
    근처(>=15:55)까지 도달한 '완성' 날짜만 사용하고, 기존 정상 봉은 덮지 않는다.
    1분봉은 야후 제약상 최근 ~7일만 커버하므로 그 이전 stale는 채우지 못한다.
    """
    if daily_df is None or daily_df.empty or "Close" not in daily_df.columns:
        return daily_df
    if intraday_df is None or intraday_df.empty:
        return daily_df

    regular = intraday_df.between_time(_REGULAR_OPEN, _REGULAR_CLOSE)
    if regular.empty:
        return daily_df

    aggregated: dict = {}
    for session_date, group in regular.groupby(regular.index.date):
        if group.index[-1].time() < _SESSION_COMPLETE_AFTER:
            continue  # 장중 미완성 세션은 일봉으로 쓰지 않음
        aggregated[session_date] = {
            "Open": float(group["Open"].iloc[0]),
            "High": float(group["High"].max()),
            "Low": float(group["Low"].min()),
            "Close": float(group["Close"].iloc[-1]),
            "Volume": float(group["Volume"].sum()),
        }
    if not aggregated:
        return daily_df

    out = daily_df.copy()
    missing = out["Close"].isna()
    for idx in out.index[missing]:
        bar = aggregated.get(idx.date())
        if bar is None:
            continue
        for column, value in bar.items():
            if column in out.columns:
                out.loc[idx, column] = value
    return out


class YFinanceProvider(BaseProvider):
    """YFinance data provider for US stocks."""

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
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "volume": info.get("volume"),
        }

    async def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Get historical price data."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._get_history_sync, ticker, period))

    def _get_history_sync(self, ticker: str, period: str) -> pd.DataFrame:
        """Synchronous history fetching. 최근 완성봉이 NaN이면 1분봉으로 백필."""
        logger.debug("yfinance get_price_history: %s (period=%s)", ticker, period)
        t = yf.Ticker(ticker)
        df = t.history(period=period)
        df = self._maybe_backfill_recent(t, df, ticker)
        logger.debug("yfinance returned %d rows for %s", len(df), ticker)
        return df

    def _maybe_backfill_recent(self, t, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """일봉 최근 구간에 NaN 완성봉이 있으면 1분봉(최근 7일) 정규장 집계로 채운다."""
        if df is None or df.empty or "Close" not in df.columns:
            return df
        if not df["Close"].tail(5).isna().any():
            return df
        try:
            intraday = t.history(period="7d", interval="1m", prepost=False)
        except Exception as exc:  # noqa: BLE001 — 백필 실패해도 원본 일봉은 그대로 반환
            logger.warning("intraday backfill fetch failed for %s: %s", ticker, exc)
            return df
        return backfill_daily_from_intraday(df, intraday)
