from __future__ import annotations

import pandas as pd


def compute_ud_volume_ratio(df: pd.DataFrame, window: int = 50) -> float | None:
    """최근 window일 상승일 거래량 합 ÷ 하락일 거래량 합. 하락일 없으면 None."""
    if "Close" not in df.columns or "Volume" not in df.columns or len(df) < 2:
        return None
    recent = df.tail(window)
    prev_close = recent["Close"].shift(1)
    up_vol = float(recent.loc[recent["Close"] > prev_close, "Volume"].sum())
    down_vol = float(recent.loc[recent["Close"] < prev_close, "Volume"].sum())
    if down_vol == 0:
        return None
    return round(up_vol / down_vol, 2)


def compute_volume_trend(vol_sma_20: float | None, vol_sma_50: float | None) -> str | None:
    """거래량 추세: 20일 평균 vs 50일 평균. ±2% 이내는 횡보."""
    if vol_sma_20 is None or vol_sma_50 is None or vol_sma_50 == 0:
        return None
    ratio = vol_sma_20 / vol_sma_50
    if ratio > 1.02:
        return "증가"
    if ratio < 0.98:
        return "감소"
    return "횡보"
