"""LEGACY_FEATURE_AD880AF numerical owner behind public compatibility wrappers.
Centered extrema describe only this supplied as-of prefix and may repaint.
"""

import numpy as np
import pandas as pd
import pandas_ta as ta
from scipy.signal import argrelextrema

from src.tools.technical.chart_analysis.features import LEGACY_VERSION, SUPPLIED_VERSION
from src.tools.technical.chart_analysis.models import SeriesInput


def legacy_features_for_series(series: SeriesInput) -> pd.DataFrame:
    """Respect explicitly supplied features; never substitute a legacy provider."""
    if series.manifest.feature_version == SUPPLIED_VERSION:
        return series.raw
    if series.manifest.feature_version != LEGACY_VERSION:
        raise ValueError("legacy features require an explicit legacy feature version")
    return calculate_legacy_features(series.raw)


def calculate_legacy_features(df: pd.DataFrame, *, crsi_calculator=None) -> pd.DataFrame:
    """Add technical indicators to DataFrame."""
    if df.empty:
        return df

    df = df.copy()

    # Flatten MultiIndex columns (yfinance single ticker returns MultiIndex)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Moving averages
    df["SMA_10"] = ta.sma(df["Close"], length=10)
    df["SMA_20"] = ta.sma(df["Close"], length=20)
    df["SMA_50"] = ta.sma(df["Close"], length=50)
    df["SMA_100"] = ta.sma(df["Close"], length=100)
    df["SMA_120"] = ta.sma(df["Close"], length=120)
    df["SMA_150"] = ta.sma(df["Close"], length=150)
    df["SMA_200"] = ta.sma(df["Close"], length=200)

    # RSI
    df["RSI"] = ta.rsi(df["Close"], length=14)

    # MACD
    macd = ta.macd(df["Close"])
    if macd is not None:
        df = pd.concat([df, macd], axis=1)
        # Rename to clear names
        if "MACD_12_26_9" in df.columns:
            df["MACD"] = df["MACD_12_26_9"]
            df["MACD_Signal"] = df["MACDs_12_26_9"]
            df["MACD_Hist"] = df["MACDh_12_26_9"]
            df = df.drop(columns=["MACD_12_26_9", "MACDs_12_26_9", "MACDh_12_26_9"])

    # Bollinger Bands
    bb = ta.bbands(df["Close"], length=20)
    if bb is not None:
        df = pd.concat([df, bb], axis=1)
        # Rename to clear names
        # Note: pandas_ta uses BBU_20_2.0_2.0 format (length_stdev_offset)
        bb_cols = [c for c in df.columns if c.startswith("BBU_20") or c.startswith("BBL_20")]
        if bb_cols:
            if any(c.startswith("BBU_20") for c in bb_cols):
                bbu_col = next(c for c in bb_cols if c.startswith("BBU_20"))
                df["BB_Upper"] = df[bbu_col]
            if any(c.startswith("BBL_20") for c in bb_cols):
                bbl_col = next(c for c in bb_cols if c.startswith("BBL_20"))
                df["BB_Lower"] = df[bbl_col]
            # Drop old columns
            df = df.drop(columns=list(bb_cols))

    # ADX
    adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
    if adx is not None:
        df = pd.concat([df, adx], axis=1)
        # Rename to clear name
        if "ADX_14" in df.columns:
            df["ADX"] = df["ADX_14"]
            df = df.drop(columns=["ADX_14"])

    # ATR
    df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

    # Stochastic
    stoch = ta.stoch(df["High"], df["Low"], df["Close"], k=14, d=3, smooth_k=3)
    if stoch is not None:
        df = pd.concat([df, stoch], axis=1)

    # CCI
    df["CCI_14_0.015"] = ta.cci(df["High"], df["Low"], df["Close"], length=14)

    # Supertrend
    st = ta.supertrend(df["High"], df["Low"], df["Close"], length=10, multiplier=3.0)
    if st is not None:
        df = pd.concat([df, st], axis=1)
        # Rename to clear names
        if "SUPERTl_10_3.0" in df.columns:
            df["SuperTrend_Up"] = df["SUPERTl_10_3.0"]
            df["SuperTrend_Dn"] = df["SUPERTs_10_3.0"]
            df["SuperTrend_Dir"] = df["SUPERTd_10_3.0"]
            df = df.drop(
                columns=["SUPERTl_10_3.0", "SUPERTs_10_3.0", "SUPERTd_10_3.0", "SUPERT_10_3.0"]
            )

    # Disparity
    for length in [20, 50, 120]:
        sma_col = f"SMA_{length}"
        if sma_col in df.columns:
            df[f"Disparity_{length}"] = (df["Close"] / df[sma_col]) * 100

    # 52-week high/low
    df["High_52w"] = df["High"].rolling(window=252, min_periods=50).max()
    df["Low_52w"] = df["Low"].rolling(window=252, min_periods=50).min()

    # Pivot points
    prev_high = df["High"].shift(1)
    prev_low = df["Low"].shift(1)
    prev_close = df["Close"].shift(1)
    pivot = (prev_high + prev_low + prev_close) / 3
    df["Pivot"] = pivot
    df["S1"] = (2 * pivot) - prev_high
    df["R1"] = (2 * pivot) - prev_low

    # Fast MACD (5/35/5)
    macd_fast = ta.macd(df["Close"], fast=5, slow=35, signal=5)
    if macd_fast is not None:
        df = pd.concat([df, macd_fast], axis=1)
        # Rename to clear names
        if "MACD_5_35_5" in df.columns:
            df["MACD_Fast"] = df["MACD_5_35_5"]
            df["MACD_Fast_Signal"] = df["MACDs_5_35_5"]
            df["MACD_Fast_Hist"] = df["MACDh_5_35_5"]
            df = df.drop(columns=["MACD_5_35_5", "MACDs_5_35_5", "MACDh_5_35_5"])

    # Volume SMAs
    df["Vol_SMA_20"] = ta.sma(df["Volume"], length=20)
    df["Vol_SMA_50"] = ta.sma(df["Volume"], length=50)
    df["Vol_SMA_120"] = ta.sma(df["Volume"], length=120)
    # 오늘 거래량을 오늘이 빠진 평균과 비교해야 하는 규칙(구조 붕괴 판정)용.
    df["Vol_SMA_20_Prev"] = df["Volume"].rolling(20).mean().shift(1)

    df["SMA_150_Slope_21"] = df["SMA_150"] - df["SMA_150"].shift(21)
    df["SMA_20_Slope_5"] = df["SMA_20"] - df["SMA_20"].shift(5)
    # *_Prev는 오늘 봉을 뺀 창이다. 오늘 종가가 이 값을 넘으면 돌파.
    df["High_50_Prev"] = df["High"].rolling(50).max().shift(1)
    df["High_20_Prev"] = df["High"].rolling(20).max().shift(1)
    df["Low_20"] = df["Low"].rolling(20).min()
    df["Low_20_Prev"] = df["Low"].rolling(20).min().shift(1)

    # Swing High/Low using scipy.signal.argrelextrema for accurate peak detection
    # order=5 means comparing with 5 points on each side (11-bar window total)
    df["Swing_High"] = np.nan
    df["Swing_Low"] = np.nan

    if len(df) >= 11:  # Need minimum data for order=5
        # Find local maxima (swing highs)
        high_values = df["High"].values
        swing_high_idx = argrelextrema(high_values, np.greater, order=5)[0]
        if len(swing_high_idx) > 0:
            df.loc[df.index[swing_high_idx], "Swing_High"] = df.iloc[swing_high_idx]["High"].values

        # Find local minima (swing lows)
        low_values = df["Low"].values
        swing_low_idx = argrelextrema(low_values, np.less, order=5)[0]
        if len(swing_low_idx) > 0:
            df.loc[df.index[swing_low_idx], "Swing_Low"] = df.iloc[swing_low_idx]["Low"].values

    # Gap detection
    prev_high = df["High"].shift(1)
    prev_low = df["Low"].shift(1)
    df["Is_Gap_Up"] = df["Low"] > prev_high
    df["Is_Gap_Down"] = df["High"] < prev_low
    df["Gap_Up_Lower"] = prev_high.where(df["Is_Gap_Up"])
    df["Gap_Down_Upper"] = prev_low.where(df["Is_Gap_Down"])

    # Cycle RSI (cRSI)
    df = (crsi_calculator or _calculate_crsi)(df)

    return df


def _calculate_crsi(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Cycle-Tuned RSI with dynamic bands."""
    rsi_10 = ta.rsi(df["Close"], length=10)
    if rsi_10 is None or rsi_10.isna().all():
        df["cRSI"] = np.nan
        df["cRSI_HighBand"] = np.nan
        df["cRSI_LowBand"] = np.nan
        return df

    dominant_cycle = 20
    vibration = 10
    torque = 2.0 / (vibration + 1)
    lag = int((vibration - 1) / 2)

    rsi_values = rsi_10.values
    crsi = np.full(len(rsi_values), np.nan)

    # Find first valid RSI index
    first_valid = rsi_10.first_valid_index()
    if first_valid is None:
        df["cRSI"] = np.nan
        df["cRSI_HighBand"] = np.nan
        df["cRSI_LowBand"] = np.nan
        return df

    start_idx = df.index.get_loc(first_valid)
    if start_idx + lag < len(rsi_values):
        crsi[start_idx + lag] = rsi_values[start_idx + lag]

    for i in range(start_idx + lag + 1, len(rsi_values)):
        if np.isnan(rsi_values[i]) or np.isnan(rsi_values[i - lag]):
            continue
        prev_crsi = crsi[i - 1] if not np.isnan(crsi[i - 1]) else rsi_values[i]
        crsi[i] = torque * (2 * rsi_values[i] - rsi_values[i - lag]) + (1 - torque) * prev_crsi

    df["cRSI"] = crsi

    # Dynamic bands (10th/90th percentile over 40-bar lookback)
    lookback = 2 * dominant_cycle
    crsi_series = pd.Series(crsi, index=df.index)
    df["cRSI_LowBand"] = crsi_series.rolling(window=lookback, min_periods=10).quantile(0.10)
    df["cRSI_HighBand"] = crsi_series.rolling(window=lookback, min_periods=10).quantile(0.90)

    return df
