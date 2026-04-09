import pandas as pd
import numpy as np

SOURCE_WEIGHTS = {
    "theme": 1.0,
    "volume_rank": 1.5,
    "rise_rank": 1.0,
    "kis_rank": 1.5,
    "direct": 0.0,
}


def score_accumulation(investor_trends: list[dict]) -> float:
    """Score based on foreign+institution net buy days. Range: 0-15."""
    if not investor_trends:
        return 0.0

    positive_days = sum(1 for t in investor_trends if t.get("total_net", 0) > 0)
    net_sum = sum(t.get("total_net", 0) for t in investor_trends)

    if net_sum <= 0:
        return 0.0

    return min(15.0, positive_days * 1.5)


def score_up_days(df: pd.DataFrame, window: int = 10) -> int:
    """Count up days (Close > Open) in recent window. Not scored, collected only."""
    if df.empty or len(df) < 2:
        return 0

    recent = df.tail(window)
    return int((recent["Close"] > recent["Open"]).sum())


def score_volume_burst(vol_ratio: float) -> float:
    """Score based on volume surge ratio. Range: 0-8."""
    if vol_ratio < 1.5:
        return 0.0
    return min(8.0, vol_ratio - 1.5)


def score_source_diversity(sources: list[str]) -> float:
    """Score based on how many data sources found this stock. Range: 0-10."""
    weighted_sum = sum(SOURCE_WEIGHTS.get(s, 0) for s in sources)
    raw = max(0, weighted_sum - 1.0)
    return min(10.0, 2.0 * raw)


def score_momentum(df: pd.DataFrame, lookback: int = 50) -> dict:
    """Score momentum signals. Returns dict with individual scores and total."""
    result = {
        "breakout": 0.0,
        "trend_reversal": 0.0,
        "compression": 0.0,
        "flow": 0.0,
        "combo": 0.0,
        "momentum_total": 0.0,
    }

    if df.empty or len(df) <= lookback:
        return result

    required_cols = {"Open", "High", "Low", "Close"}
    if not required_cols.issubset(df.columns):
        return result

    latest = df.iloc[-1]
    close = float(latest["Close"])

    # Breakout: close > previous N days high
    prev_high = df["High"].iloc[-(lookback + 1):-1].max()
    if not pd.isna(prev_high) and close > float(prev_high):
        result["breakout"] = 12.0

    # Trend Reversal: SuperTrend direction change -1 → +1
    if "SUPERTd_10_3.0" in df.columns and len(df) > 1:
        curr_dir = df.iloc[-1].get("SUPERTd_10_3.0")
        prev_dir = df.iloc[-2].get("SUPERTd_10_3.0")
        if not pd.isna(curr_dir) and not pd.isna(prev_dir):
            if float(prev_dir) < 0 and float(curr_dir) > 0:
                result["trend_reversal"] = 25.0

    # Compression: recent 10-day ATR < previous 10-day ATR
    if "ATR" in df.columns and len(df) >= 20:
        recent_atr = df["ATR"].iloc[-10:].mean()
        prev_atr = df["ATR"].iloc[-20:-10].mean()
        if not pd.isna(recent_atr) and not pd.isna(prev_atr) and prev_atr > 0:
            if recent_atr < prev_atr:
                result["compression"] = 15.0

    # Combo bonus
    if result["breakout"] > 0 and result["trend_reversal"] > 0:
        result["combo"] = 10.0

    result["momentum_total"] = (
        result["breakout"]
        + result["trend_reversal"]
        + result["compression"]
        + result["flow"]
        + result["combo"]
    )

    return result
