import numpy as np
import pandas as pd

from src.tools.technical.staleness import StaleClose, drop_trailing_nan_close


def _ohlcv(closes: list[float], dates: list[str]) -> pd.DataFrame:
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c if pd.isna(c) else c + 1 for c in closes],
            "Low": [c if pd.isna(c) else c - 1 for c in closes],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=index,
    )


def test_drops_single_trailing_nan_close_row():
    df = _ohlcv([100.0, 101.0, np.nan], ["2026-09-15", "2026-09-16", "2026-09-17"])

    cleaned, stale = drop_trailing_nan_close(df)

    assert len(cleaned) == 2
    assert not cleaned["Close"].isna().any()
    assert stale.dropped_rows == 1
    assert stale.dropped_dates == ["2026-09-17"]
    assert stale.last_valid_date == "2026-09-16"
    assert stale.is_stale is True


def test_valid_last_bar_is_noop():
    df = _ohlcv([100.0, 101.0, 102.0], ["2026-09-15", "2026-09-16", "2026-09-17"])

    cleaned, stale = drop_trailing_nan_close(df)

    assert len(cleaned) == 3
    assert stale.dropped_rows == 0
    assert stale.is_stale is False
    assert stale.last_valid_date == "2026-09-17"


def test_drops_multiple_trailing_nan_rows():
    df = _ohlcv(
        [100.0, 101.0, np.nan, np.nan],
        ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"],
    )

    cleaned, stale = drop_trailing_nan_close(df)

    assert len(cleaned) == 2
    assert stale.dropped_rows == 2
    assert stale.dropped_dates == ["2026-09-16", "2026-09-17"]
    assert stale.last_valid_date == "2026-09-15"


def test_middle_nan_close_is_untouched():
    df = _ohlcv(
        [100.0, np.nan, 102.0],
        ["2026-09-15", "2026-09-16", "2026-09-17"],
    )

    cleaned, stale = drop_trailing_nan_close(df)

    assert len(cleaned) == 3
    assert stale.dropped_rows == 0
    assert stale.is_stale is False


def test_empty_df_returns_noop():
    df = pd.DataFrame({"Open": [], "High": [], "Low": [], "Close": [], "Volume": []})

    cleaned, stale = drop_trailing_nan_close(df)

    assert cleaned.empty
    assert stale.dropped_rows == 0
    assert stale.last_valid_date is None
    assert stale.is_stale is False


def test_all_nan_close_returns_empty_with_all_dropped():
    df = _ohlcv([np.nan, np.nan], ["2026-09-16", "2026-09-17"])

    cleaned, stale = drop_trailing_nan_close(df)

    assert cleaned.empty
    assert stale.dropped_rows == 2
    assert stale.last_valid_date is None
    assert stale.is_stale is True


def test_stale_close_is_frozen_dataclass():
    stale = StaleClose(dropped_rows=1, dropped_dates=["2026-09-17"], last_valid_date="2026-09-16")
    assert stale.is_stale is True
