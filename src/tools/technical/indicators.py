import pandas as pd
import pandas_ta as ta
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

        return df

    def create_snapshot(self, df: pd.DataFrame) -> IndicatorSnapshot:
        """Create indicator snapshot from latest row."""
        if df.empty:
            return IndicatorSnapshot(price=0, change_pct=0)

        latest = df.iloc[-1]
        prev_close = df.iloc[-2]["Close"] if len(df) > 1 else latest["Close"]
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
        )
