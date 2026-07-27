import pandas as pd

from src.tools.technical.models import MarketContext


def _safe_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _ret_pct(df: pd.DataFrame, days: int) -> float | None:
    if len(df) <= days:
        return None
    current = _safe_float(df.iloc[-1].get("Close"))
    previous = _safe_float(df.iloc[-days - 1].get("Close"))
    if current is None or previous in (None, 0):
        return None
    return round(((current - previous) / previous) * 100, 2)


def _distance_pct(close: float, reference: float | None) -> float | None:
    if reference in (None, 0):
        return None
    return round(((close - reference) / reference) * 100, 2)


def build_market_context(df: pd.DataFrame) -> MarketContext:
    """Build derived OHLCV state for ScoreAggregator."""
    if df.empty:
        return MarketContext(close=0.0)

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    close = _safe_float(latest.get("Close")) or 0.0

    sma20 = _safe_float(latest.get("SMA_20"))
    sma50 = _safe_float(latest.get("SMA_50"))
    sma150 = _safe_float(latest.get("SMA_150"))
    sma200 = _safe_float(latest.get("SMA_200"))
    volume = _safe_float(latest.get("Volume"))
    vol_sma20 = _safe_float(latest.get("Vol_SMA_20"))
    rsi = _safe_float(latest.get("RSI"))
    atr = _safe_float(latest.get("ATR"))
    supertrend_direction = latest.get("SuperTrend_Dir")
    previous_supertrend_direction = previous.get("SuperTrend_Dir")

    volume_ratio = None
    if volume is not None and vol_sma20 not in (None, 0):
        volume_ratio = round(volume / vol_sma20, 2)

    high_20 = _safe_float(df["High"].iloc[-20:].max()) if "High" in df.columns else None
    distance_from_20d_high_pct = None
    if high_20 not in (None, 0):
        distance_from_20d_high_pct = round(((close - high_20) / high_20) * 100, 2)

    atr_pct = None
    if atr is not None and close:
        atr_pct = round((atr / close) * 100, 2)

    supertrend_dir = None if pd.isna(supertrend_direction) else int(supertrend_direction)
    prev_supertrend_dir = (
        None if pd.isna(previous_supertrend_direction) else int(previous_supertrend_direction)
    )
    supertrend_sell_transition = prev_supertrend_dir == 1 and supertrend_dir == -1

    ret_1d = _ret_pct(df, 1)
    ret_5d = _ret_pct(df, 5)
    ret_10d = _ret_pct(df, 10)
    distance_sma20 = _distance_pct(close, sma20)
    distance_sma50 = _distance_pct(close, sma50)

    close_above_sma20 = sma20 is not None and close > sma20
    close_above_sma50 = sma50 is not None and close > sma50
    close_above_sma150 = sma150 is not None and close > sma150
    close_above_sma200 = sma200 is not None and close > sma200
    sma20_above_sma50 = sma20 is not None and sma50 is not None and sma20 > sma50

    is_overextended = any(
        [
            rsi is not None and rsi >= 75,
            ret_5d is not None and ret_5d >= 15,
            ret_1d is not None and ret_1d >= 8,
            distance_sma20 is not None and distance_sma20 >= 12,
        ]
    )
    is_breakdown = any(
        [
            close_above_sma50 is False and volume_ratio is not None and volume_ratio >= 1.3,
            supertrend_sell_transition,
            close_above_sma20 is False
            and close_above_sma50 is False
            and ret_10d is not None
            and ret_10d < 0,
        ]
    )
    is_uptrend = close_above_sma50 and sma20_above_sma50 and supertrend_dir != -1
    is_downtrend = (not close_above_sma50 and supertrend_dir == -1) or (
        sma20 is not None and sma50 is not None and sma20 < sma50 and close < sma50
    )

    support_candidates = [
        value for value in [sma20, sma50, sma150, sma200] if value and value < close
    ]
    nearest_support = max(support_candidates) if support_candidates else None

    return MarketContext(
        close=close,
        close_above_sma20=close_above_sma20,
        close_above_sma50=close_above_sma50,
        close_above_sma150=close_above_sma150,
        close_above_sma200=close_above_sma200,
        sma20_above_sma50=sma20_above_sma50,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        ret_10d=ret_10d,
        distance_from_20d_high_pct=distance_from_20d_high_pct,
        distance_from_sma20_pct=distance_sma20,
        distance_from_sma50_pct=distance_sma50,
        volume_ratio_20d=volume_ratio,
        rsi=rsi,
        atr_pct=atr_pct,
        supertrend_direction=supertrend_dir,
        supertrend_sell_transition=supertrend_sell_transition,
        is_overextended=is_overextended,
        is_breakdown=is_breakdown,
        is_uptrend=is_uptrend,
        is_downtrend=is_downtrend,
        nearest_support=nearest_support,
    )
