from __future__ import annotations

import pandas as pd

from src.tools.technical.events_models import (
    MacdCross,
)


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


def detect_macd_cross(df: pd.DataFrame, lookback: int = 60) -> MacdCross | None:
    """최근 lookback일 내 가장 최근 MACD-시그널 교차. 없으면 None."""
    if "MACD" not in df.columns or "MACD_Signal" not in df.columns:
        return None
    recent = df.tail(lookback).dropna(subset=["MACD", "MACD_Signal"])
    if len(recent) < 2:
        return None
    diff = recent["MACD"] - recent["MACD_Signal"]
    sign = diff.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    for i in range(len(sign) - 1, 0, -1):
        cur, prev = sign.iloc[i], sign.iloc[i - 1]
        if cur != 0 and prev != 0 and cur != prev:
            cross_date = recent.index[i]
            days_ago = len(df) - 1 - df.index.get_loc(cross_date)
            return MacdCross(
                cross_type="golden" if cur > 0 else "dead",
                date=cross_date.strftime("%Y-%m-%d"),
                days_ago=int(days_ago),
                macd=round(float(recent["MACD"].iloc[i]), 4),
                signal=round(float(recent["MACD_Signal"].iloc[i]), 4),
            )
    return None
