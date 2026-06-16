from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.providers.yfinance_provider import YFinanceProvider


@pytest.mark.asyncio
async def test_get_quote():
    provider = YFinanceProvider()

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "currentPrice": 178.50,
        "previousClose": 175.00,
        "shortName": "Apple Inc.",
    }

    with patch("yfinance.Ticker", return_value=mock_ticker):
        quote = await provider.get_quote("AAPL")

    assert quote["price"] == 178.50
    assert quote["previous_close"] == 175.00
    assert quote["name"] == "Apple Inc."


@pytest.mark.asyncio
async def test_get_price_history():
    provider = YFinanceProvider()

    mock_df = pd.DataFrame(
        {
            "Open": [170.0, 172.0],
            "High": [175.0, 178.0],
            "Low": [169.0, 171.0],
            "Close": [174.0, 177.0],
            "Volume": [1000000, 1200000],
        }
    )

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_df

    with patch("yfinance.Ticker", return_value=mock_ticker):
        df = await provider.get_price_history("AAPL", "1y")

    assert len(df) == 2
    assert "Close" in df.columns
    mock_ticker.history.assert_called_once_with(period="1y")


def _reg_1m(
    date: str, *, open0: float, high: float, low: float, close_last: float, end: str = "16:00"
):
    """주어진 날짜의 정규장 1분봉 합성 (09:30~end)."""
    idx = pd.date_range(f"{date} 09:30", f"{date} {end}", freq="1min", tz="America/New_York")
    n = len(idx)
    opens = [open0] + [(open0 + close_last) / 2] * (n - 1)
    closes = [(open0 + close_last) / 2] * (n - 1) + [close_last]
    highs = [(open0 + close_last) / 2] * n
    lows = [(open0 + close_last) / 2] * n
    highs[n // 2] = high
    lows[n // 3] = low
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": [1000.0] * n},
        index=idx,
    )


def test_backfill_fills_nan_daily_bar_from_regular_session():
    import numpy as np

    from src.providers.yfinance_provider import backfill_daily_from_intraday

    daily = pd.DataFrame(
        {
            "Open": [360.0, float("nan")],
            "High": [368.0, float("nan")],
            "Low": [359.0, float("nan")],
            "Close": [367.15, float("nan")],
            "Volume": [4_000_000.0, float("nan")],
        },
        index=pd.DatetimeIndex(["2026-06-12", "2026-06-15"], tz="America/New_York"),
    )
    intraday = _reg_1m("2026-06-15", open0=382.5, high=398.13, low=364.41, close_last=389.2)

    out = backfill_daily_from_intraday(daily, intraday)

    j15 = pd.Timestamp("2026-06-15", tz="America/New_York")
    assert not np.isnan(out.loc[j15, "Close"])
    assert out.loc[j15, "Close"] == 389.2
    assert out.loc[j15, "Open"] == 382.5
    assert out.loc[j15, "High"] == 398.13
    assert out.loc[j15, "Low"] == 364.41


def test_backfill_skips_incomplete_session():
    import numpy as np

    from src.providers.yfinance_provider import backfill_daily_from_intraday

    daily = pd.DataFrame(
        {
            "Open": [float("nan")],
            "High": [float("nan")],
            "Low": [float("nan")],
            "Close": [float("nan")],
            "Volume": [float("nan")],
        },
        index=pd.DatetimeIndex(["2026-06-16"], tz="America/New_York"),
    )
    # 장중 11:00까지만 → 미완성 세션
    intraday = _reg_1m(
        "2026-06-16", open0=390.0, high=392.0, low=388.0, close_last=391.0, end="11:00"
    )

    out = backfill_daily_from_intraday(daily, intraday)

    j16 = pd.Timestamp("2026-06-16", tz="America/New_York")
    assert np.isnan(out.loc[j16, "Close"])


def test_backfill_does_not_overwrite_existing_bar():
    from src.providers.yfinance_provider import backfill_daily_from_intraday

    daily = pd.DataFrame(
        {
            "Open": [360.0],
            "High": [368.0],
            "Low": [359.0],
            "Close": [367.15],
            "Volume": [4_000_000.0],
        },
        index=pd.DatetimeIndex(["2026-06-12"], tz="America/New_York"),
    )
    intraday = _reg_1m("2026-06-12", open0=377.0, high=390.0, low=360.0, close_last=999.0)

    out = backfill_daily_from_intraday(daily, intraday)

    j12 = pd.Timestamp("2026-06-12", tz="America/New_York")
    assert out.loc[j12, "Close"] == 367.15  # 기존 정상 봉은 덮지 않음
