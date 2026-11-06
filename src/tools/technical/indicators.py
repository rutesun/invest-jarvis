import pandas as pd

from src.tools.technical.models import IndicatorSnapshot


class IndicatorCalculator:
    """Calculate technical indicators from OHLCV data."""

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to DataFrame."""
        from src.tools.technical.chart_analysis import legacy_features

        return legacy_features.calculate_legacy_features(df, crsi_calculator=self._calculate_crsi)

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

        # Calculate performance over different periods
        current_price = float(latest["Close"])
        perf_1m = self._calculate_performance(df_clean, current_price, days=21)
        perf_3m = self._calculate_performance(df_clean, current_price, days=63)
        perf_6m = self._calculate_performance(df_clean, current_price, days=126)
        perf_1y = self._calculate_performance(df_clean, current_price, days=252)

        def safe_get(key: str) -> float | None:
            val = latest.get(key)
            if pd.isna(val):
                return None
            return float(val)

        return IndicatorSnapshot(
            price=float(latest["Close"]),
            change_pct=round(change_pct, 2),
            perf_1m=perf_1m,
            perf_3m=perf_3m,
            perf_6m=perf_6m,
            perf_1y=perf_1y,
            sma_10=safe_get("SMA_10"),
            sma_20=safe_get("SMA_20"),
            sma_50=safe_get("SMA_50"),
            sma_100=safe_get("SMA_100"),
            sma_120=safe_get("SMA_120"),
            sma_200=safe_get("SMA_200"),
            sma_20_slope_pct=self._slope_pct(df, "SMA_20"),
            sma_50_slope_pct=self._slope_pct(df, "SMA_50"),
            sma_100_slope_pct=self._slope_pct(df, "SMA_100"),
            sma_150_slope_pct=self._slope_pct(df, "SMA_150"),
            sma_200_slope_pct=self._slope_pct(df, "SMA_200"),
            rsi=safe_get("RSI"),
            macd=safe_get("MACD"),
            macd_signal=safe_get("MACD_Signal"),
            macd_histogram=safe_get("MACD_Hist"),
            atr=safe_get("ATR"),
            bb_upper=safe_get("BB_Upper"),
            bb_lower=safe_get("BB_Lower"),
            adx=safe_get("ADX"),
            supertrend_direction=int(safe_get("SuperTrend_Dir") or 0)
            if safe_get("SuperTrend_Dir")
            else None,
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
            is_gap_up=bool(latest.get("Is_Gap_Up"))
            if not pd.isna(latest.get("Is_Gap_Up"))
            else None,
            is_gap_down=bool(latest.get("Is_Gap_Down"))
            if not pd.isna(latest.get("Is_Gap_Down"))
            else None,
            macd_fast=safe_get("MACD_Fast"),
            macd_fast_signal=safe_get("MACD_Fast_Signal"),
            macd_fast_histogram=safe_get("MACD_Fast_Hist"),
        )

    @staticmethod
    def _slope_pct(df: pd.DataFrame, column: str, lookback: int = 21) -> float | None:
        if column not in df.columns or len(df) <= lookback:
            return None
        current = df[column].iloc[-1]
        previous = df[column].iloc[-lookback - 1]
        if pd.isna(current) or pd.isna(previous) or previous == 0:
            return None
        return float((current / previous - 1.0) * 100.0)

    def _calculate_performance(
        self, df: pd.DataFrame, current_price: float, days: int
    ) -> float | None:
        """Calculate performance over specified number of trading days."""
        if len(df) <= days:
            return None
        past_price = df.iloc[-days]["Close"]
        if pd.isna(past_price) or past_price == 0:
            return None
        return round(((current_price - past_price) / past_price) * 100, 2)

    def _calculate_crsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Cycle-Tuned RSI with dynamic bands."""
        from src.tools.technical.chart_analysis import legacy_features

        return legacy_features._calculate_crsi(df)
