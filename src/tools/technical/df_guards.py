"""DataFrame guards against trailing NaN (current-day incomplete bars).

yfinance daily feeds can place a NaN Close on the last row (today's bar not yet
finalized). Consumers that read iloc[-1] without guarding silently propagate NaN,
and NaN comparisons are always False — which mutes breakout/stop signals.
"""

from __future__ import annotations

import pandas as pd


def last_valid_close(df: pd.DataFrame) -> float | None:
    """Return the last non-NaN Close, skipping a trailing incomplete bar.

    Returns None when there is no Close column or no valid value at all.
    """
    if df is None or "Close" not in df.columns:
        return None
    s = df["Close"].dropna()
    return float(s.iloc[-1]) if not s.empty else None
