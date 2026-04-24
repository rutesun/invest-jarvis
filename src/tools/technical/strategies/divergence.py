import numpy as np
import pandas as pd

from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class DivergenceStrategy(BaseStrategy):
    """Divergence analysis between price and indicators."""

    name = "divergence"
    description = "가격과 지표 간 다이버전스 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 30:
            return self._neutral_result("데이터 부족")

        signals = []
        evidence = []
        metrics = {}
        score = 0

        # Check RSI divergence
        rsi_div = self._check_rsi_divergence(df)
        if rsi_div:
            score += rsi_div["score"]
            signals.append(rsi_div["signal"])
            evidence.append(rsi_div["evidence"])

        # Check MACD divergence
        macd_div = self._check_macd_divergence(df)
        if macd_div:
            score += macd_div["score"]
            signals.append(macd_div["signal"])
            evidence.append(macd_div["evidence"])

        # Determine status
        if score > 20:
            status = "강세"
        elif score < -20:
            status = "약세"
        else:
            status = "중립"

        confidence = min(100, max(0, 50 + abs(score) * 2))

        return StrategyResult(
            name=self.name,
            status=status,
            confidence=confidence,
            signals=signals,
            evidence=evidence,
            metrics=metrics,
        )

    def _check_rsi_divergence(self, df: pd.DataFrame) -> dict | None:
        """Check RSI divergence."""
        if "RSI" not in df.columns:
            return None

        recent = df.tail(20)
        price_peaks = self._find_peaks(recent["Close"].values)
        rsi_peaks = self._find_peaks(recent["RSI"].values)

        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            # Bullish divergence: price lower lows, RSI higher lows
            if (
                recent["Close"].iloc[price_peaks[-1]] < recent["Close"].iloc[price_peaks[-2]]
                and recent["RSI"].iloc[rsi_peaks[-1]] > recent["RSI"].iloc[rsi_peaks[-2]]
            ):
                return {
                    "signal": "RSI 강세 다이버전스",
                    "evidence": "가격 저점 하락, RSI 저점 상승",
                    "score": 25,
                }
            # Bearish divergence: price higher highs, RSI lower highs
            elif (
                recent["Close"].iloc[price_peaks[-1]] > recent["Close"].iloc[price_peaks[-2]]
                and recent["RSI"].iloc[rsi_peaks[-1]] < recent["RSI"].iloc[rsi_peaks[-2]]
            ):
                return {
                    "signal": "RSI 약세 다이버전스",
                    "evidence": "가격 고점 상승, RSI 고점 하락",
                    "score": -25,
                }

        return None

    def _check_macd_divergence(self, df: pd.DataFrame) -> dict | None:
        """Check MACD divergence."""
        if "MACD" not in df.columns:
            return None

        recent = df.tail(20)
        price_peaks = self._find_peaks(recent["Close"].values)
        macd_peaks = self._find_peaks(recent["MACD"].values)

        if len(price_peaks) >= 2 and len(macd_peaks) >= 2:
            # Bullish divergence
            if (
                recent["Close"].iloc[price_peaks[-1]] < recent["Close"].iloc[price_peaks[-2]]
                and recent["MACD"].iloc[macd_peaks[-1]] > recent["MACD"].iloc[macd_peaks[-2]]
            ):
                return {
                    "signal": "MACD 강세 다이버전스",
                    "evidence": "가격 저점 하락, MACD 저점 상승",
                    "score": 20,
                }
            # Bearish divergence
            elif (
                recent["Close"].iloc[price_peaks[-1]] > recent["Close"].iloc[price_peaks[-2]]
                and recent["MACD"].iloc[macd_peaks[-1]] < recent["MACD"].iloc[macd_peaks[-2]]
            ):
                return {
                    "signal": "MACD 약세 다이버전스",
                    "evidence": "가격 고점 상승, MACD 고점 하락",
                    "score": -20,
                }

        return None

    def _find_peaks(self, data: np.ndarray) -> list[int]:
        """Find local peaks in data."""
        peaks = []
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1]:
                peaks.append(i)
        return peaks

    def _neutral_result(self, reason: str) -> StrategyResult:
        return StrategyResult(
            name=self.name,
            status="중립",
            confidence=50.0,
            signals=[],
            evidence=[reason],
            metrics={},
        )
