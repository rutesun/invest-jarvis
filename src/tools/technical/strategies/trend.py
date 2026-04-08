import pandas as pd
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class TrendStrategy(BaseStrategy):
    """Trend analysis using moving averages, ADX, and supertrend."""

    name = "trend"
    description = "이동평균, ADX, 슈퍼트렌드 기반 추세 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 50:
            return self._neutral_result("데이터 부족")

        latest = df.iloc[-1]
        signals = []
        evidence = []
        metrics = {}
        score = 0

        # Get values safely
        close = self._safe_get(latest, "Close")
        sma_20 = self._safe_get(latest, "SMA_20")
        sma_50 = self._safe_get(latest, "SMA_50")
        sma_200 = self._safe_get(latest, "SMA_200")
        adx = self._safe_get(latest, "ADX_14")
        supertrend_dir = self._safe_get(latest, "SUPERTd_10_3.0")

        # Store metrics
        metrics["close"] = close
        if sma_20:
            metrics["sma_20"] = round(sma_20, 2)
        if sma_50:
            metrics["sma_50"] = round(sma_50, 2)
        if sma_200:
            metrics["sma_200"] = round(sma_200, 2)
        if adx:
            metrics["adx"] = round(adx, 2)

        # Price vs SMA analysis
        if sma_20 and close > sma_20:
            score += 20
            evidence.append(f"가격({close:.2f}) > 20일선({sma_20:.2f})")
        elif sma_20 and close < sma_20:
            score -= 20
            evidence.append(f"가격({close:.2f}) < 20일선({sma_20:.2f})")

        if sma_50 and close > sma_50:
            score += 15
            evidence.append(f"가격 > 50일선({sma_50:.2f})")
        elif sma_50 and close < sma_50:
            score -= 15
            evidence.append(f"가격 < 50일선({sma_50:.2f})")

        if sma_200 and close > sma_200:
            score += 10
            evidence.append(f"가격 > 200일선({sma_200:.2f})")
        elif sma_200 and close < sma_200:
            score -= 10
            evidence.append(f"가격 < 200일선({sma_200:.2f})")

        # Golden/Death cross
        if sma_20 and sma_50:
            prev_sma_20 = self._safe_get(df.iloc[-2], "SMA_20") if len(df) > 1 else 0
            prev_sma_50 = self._safe_get(df.iloc[-2], "SMA_50") if len(df) > 1 else 0

            if prev_sma_20 < prev_sma_50 and sma_20 > sma_50:
                signals.append("골든크로스")
                score += 25
            elif prev_sma_20 > prev_sma_50 and sma_20 < sma_50:
                signals.append("데드크로스")
                score -= 25

            if sma_20 > sma_50:
                evidence.append("20일선 > 50일선 (정배열)")
                score += 10
            else:
                evidence.append("20일선 < 50일선 (역배열)")
                score -= 10

        # ADX trend strength
        if adx:
            if adx > 25:
                evidence.append(f"ADX {adx:.1f} (강한 추세)")
                score += 10 if score > 0 else -10  # amplify existing trend
            else:
                evidence.append(f"ADX {adx:.1f} (약한 추세)")

        # Supertrend
        if supertrend_dir:
            if supertrend_dir > 0:
                signals.append("슈퍼트렌드 상승")
                score += 15
            else:
                signals.append("슈퍼트렌드 하락")
                score -= 15

        # Determine status and confidence
        if score > 30:
            status = "강세"
        elif score > 10:
            status = "약강세"
        elif score < -30:
            status = "약세"
        elif score < -10:
            status = "약약세"
        else:
            status = "중립"

        confidence = min(100, max(0, 50 + score))

        return StrategyResult(
            name=self.name,
            status=status,
            confidence=confidence,
            signals=signals,
            evidence=evidence,
            metrics=metrics,
        )

    def _neutral_result(self, reason: str) -> StrategyResult:
        return StrategyResult(
            name=self.name,
            status="중립",
            confidence=50.0,
            signals=[],
            evidence=[reason],
            metrics={},
        )
