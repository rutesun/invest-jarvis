import pandas as pd
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class OscillatorStrategy(BaseStrategy):
    """Oscillator analysis using RSI, Stochastic, CCI."""

    name = "oscillator"
    description = "RSI, 스토캐스틱, CCI 기반 모멘텀 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 20:
            return self._neutral_result("데이터 부족")

        latest = df.iloc[-1]
        signals = []
        evidence = []
        metrics = {}
        score = 0

        # RSI
        rsi = self._safe_get(latest, "RSI")
        if rsi:
            metrics["rsi"] = round(rsi, 2)
            if rsi > 70:
                signals.append("RSI 과매수")
                evidence.append(f"RSI {rsi:.1f} > 70")
                score -= 20
            elif rsi < 30:
                signals.append("RSI 과매도")
                evidence.append(f"RSI {rsi:.1f} < 30")
                score += 20
            elif 40 <= rsi <= 60:
                evidence.append(f"RSI {rsi:.1f} (중립권)")

        # Stochastic (if available)
        stoch_k = self._safe_get(latest, "STOCHk_14_3_3")
        stoch_d = self._safe_get(latest, "STOCHd_14_3_3")
        if stoch_k and stoch_d:
            metrics["stoch_k"] = round(stoch_k, 2)
            metrics["stoch_d"] = round(stoch_d, 2)

            if stoch_k > 80:
                signals.append("스토캐스틱 과매수")
                evidence.append(f"Stochastic K {stoch_k:.1f} > 80")
                score -= 15
            elif stoch_k < 20:
                signals.append("스토캐스틱 과매도")
                evidence.append(f"Stochastic K {stoch_k:.1f} < 20")
                score += 15

            # Golden/Death cross
            if len(df) > 1:
                prev_k = self._safe_get(df.iloc[-2], "STOCHk_14_3_3")
                prev_d = self._safe_get(df.iloc[-2], "STOCHd_14_3_3")
                if prev_k and prev_d:
                    if prev_k < prev_d and stoch_k > stoch_d and stoch_k < 50:
                        signals.append("스토캐스틱 골든크로스")
                        score += 15
                    elif prev_k > prev_d and stoch_k < stoch_d and stoch_k > 50:
                        signals.append("스토캐스틱 데드크로스")
                        score -= 15

        # CCI
        cci = self._safe_get(latest, "CCI_14_0.015")
        if cci:
            metrics["cci"] = round(cci, 2)
            if cci > 100:
                signals.append("CCI 과매수")
                evidence.append(f"CCI {cci:.1f} > 100")
                score -= 10
            elif cci < -100:
                signals.append("CCI 과매도")
                evidence.append(f"CCI {cci:.1f} < -100")
                score += 10

        # Determine status
        if score > 30:
            status = "과매도"
        elif score > 10:
            status = "약과매도"
        elif score < -30:
            status = "과매수"
        elif score < -10:
            status = "약과매수"
        else:
            status = "중립"

        confidence = min(100, max(0, 50 + abs(score)))

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
