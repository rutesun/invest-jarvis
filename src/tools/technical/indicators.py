import pandas as pd
import pandas_ta as ta
import numpy as np
from scipy.signal import argrelextrema
from src.tools.technical.models import IndicatorSnapshot


class IndicatorCalculator:
    """Calculate technical indicators from OHLCV data."""

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to DataFrame."""
        if df.empty:
            return df

        df = df.copy()

        # Moving averages
        df["SMA_10"] = ta.sma(df["Close"], length=10)
        df["SMA_20"] = ta.sma(df["Close"], length=20)
        df["SMA_50"] = ta.sma(df["Close"], length=50)
        df["SMA_120"] = ta.sma(df["Close"], length=120)
        df["SMA_150"] = ta.sma(df["Close"], length=150)
        df["SMA_200"] = ta.sma(df["Close"], length=200)

        # RSI
        df["RSI"] = ta.rsi(df["Close"], length=14)

        # MACD
        macd = ta.macd(df["Close"])
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        # Bollinger Bands
        bb = ta.bbands(df["Close"], length=20)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)

        # ADX
        adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx is not None:
            df = pd.concat([df, adx], axis=1)

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

        # Volume SMAs
        df["Vol_SMA_20"] = ta.sma(df["Volume"], length=20)
        df["Vol_SMA_50"] = ta.sma(df["Volume"], length=50)
        df["Vol_SMA_120"] = ta.sma(df["Volume"], length=120)

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
        df = self._calculate_crsi(df)

        return df

    def create_snapshot(self, df: pd.DataFrame) -> IndicatorSnapshot:
        """Create indicator snapshot from latest row."""
        if df.empty:
            return IndicatorSnapshot(price=0, change_pct=0)

        # Drop rows with NaN Close values to get valid latest data
        df_clean = df.dropna(subset=["Close"])
        if df_clean.empty:
            return IndicatorSnapshot(price=0, change_pct=0)

        latest = df_clean.iloc[-1]
        prev_close = df_clean.iloc[-2]["Close"] if len(df_clean) > 1 else latest["Close"]
        change_pct = ((latest["Close"] - prev_close) / prev_close) * 100

        def safe_get(key: str) -> float | None:
            val = latest.get(key)
            if pd.isna(val):
                return None
            return float(val)

        return IndicatorSnapshot(
            price=float(latest["Close"]),
            change_pct=round(change_pct, 2),
            sma_10=safe_get("SMA_10"),
            sma_20=safe_get("SMA_20"),
            sma_50=safe_get("SMA_50"),
            sma_120=safe_get("SMA_120"),
            sma_200=safe_get("SMA_200"),
            rsi=safe_get("RSI"),
            macd=safe_get("MACD_12_26_9"),
            macd_signal=safe_get("MACDs_12_26_9"),
            macd_histogram=safe_get("MACDh_12_26_9"),
            atr=safe_get("ATR"),
            bb_upper=safe_get("BBU_20_2.0"),
            bb_lower=safe_get("BBL_20_2.0"),
            adx=safe_get("ADX_14"),
            supertrend_direction=int(safe_get("SUPERTd_10_3.0") or 0) if safe_get("SUPERTd_10_3.0") else None,
            disparity_20=safe_get("Disparity_20"),
            disparity_50=safe_get("Disparity_50"),
            disparity_120=safe_get("Disparity_120"),
            pivot=safe_get("Pivot"),
            support_s1=safe_get("S1"),
            resistance_r1=safe_get("R1"),
            high_52w=safe_get("High_52w"),
            low_52w=safe_get("Low_52w"),
            sma_150=safe_get("SMA_150"),
            crsi=safe_get("cRSI"),
            crsi_high_band=safe_get("cRSI_HighBand"),
            crsi_low_band=safe_get("cRSI_LowBand"),
            vol_sma_20=safe_get("Vol_SMA_20"),
            vol_sma_50=safe_get("Vol_SMA_50"),
            vol_sma_120=safe_get("Vol_SMA_120"),
            swing_high=safe_get("Swing_High"),
            swing_low=safe_get("Swing_Low"),
            is_gap_up=bool(latest.get("Is_Gap_Up")) if not pd.isna(latest.get("Is_Gap_Up")) else None,
            is_gap_down=bool(latest.get("Is_Gap_Down")) if not pd.isna(latest.get("Is_Gap_Down")) else None,
            macd_fast=safe_get("MACD_5_35_5"),
            macd_fast_signal=safe_get("MACDs_5_35_5"),
            macd_fast_histogram=safe_get("MACDh_5_35_5"),
        )

    def _calculate_crsi(self, df: pd.DataFrame) -> pd.DataFrame:
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
