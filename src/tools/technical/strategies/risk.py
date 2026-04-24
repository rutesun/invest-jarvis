import pandas as pd

from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class RiskStrategy(BaseStrategy):
    """변동성 및 리스크 분석."""

    name = "risk"
    description = "ATR, 볼린저밴드, 52주 고저점 기반 리스크 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 50:
            return self._neutral_result("데이터 부족")

        latest = df.iloc[-1]
        signals = []
        evidence = []
        metrics = {}
        score = 0

        close = self._safe_get(latest, "Close")
        atr = self._safe_get(latest, "ATR")
        bb_upper = self._safe_get(latest, "BB_Upper")
        bb_lower = self._safe_get(latest, "BB_Lower")
        high_52w = self._safe_get(latest, "High_52w")
        low_52w = self._safe_get(latest, "Low_52w")

        # ATR analysis (normalized by price)
        if atr and close:
            atr_pct = (atr / close) * 100
            metrics["atr_pct"] = round(atr_pct, 2)

            if atr_pct > 5:
                signals.append("고변동성")
                evidence.append(f"ATR {atr_pct:.1f}% (>5%)")
                score += 30
            elif atr_pct > 3:
                signals.append("중변동성")
                evidence.append(f"ATR {atr_pct:.1f}% (3-5%)")
                score += 15
            else:
                evidence.append(f"ATR {atr_pct:.1f}% (저변동성)")

        # Bollinger Bands width
        if bb_upper and bb_lower and close:
            bb_width = ((bb_upper - bb_lower) / close) * 100
            metrics["bb_width_pct"] = round(bb_width, 2)

            if bb_width > 10:
                signals.append("볼린저밴드 확장")
                evidence.append(f"BB 폭 {bb_width:.1f}% (고변동)")
                score += 20
            elif bb_width < 5:
                signals.append("볼린저밴드 수축")
                evidence.append(f"BB 폭 {bb_width:.1f}% (저변동)")
                score -= 10
            else:
                evidence.append(f"BB 폭 {bb_width:.1f}% (정상)")

            # Position within bands
            if close > bb_upper:
                signals.append("밴드 상단 돌파")
                evidence.append("가격이 볼린저밴드 상단 초과")
                score += 10
            elif close < bb_lower:
                signals.append("밴드 하단 돌파")
                evidence.append("가격이 볼린저밴드 하단 미만")
                score += 10

        # 52-week high/low distance
        if high_52w and low_52w and close:
            range_52w = high_52w - low_52w
            if range_52w > 0:
                dist_from_high = ((high_52w - close) / range_52w) * 100
                dist_from_low = ((close - low_52w) / range_52w) * 100

                metrics["dist_from_52w_high_pct"] = round(dist_from_high, 1)
                metrics["dist_from_52w_low_pct"] = round(dist_from_low, 1)

                if dist_from_high < 5:
                    signals.append("52주 고점 근접")
                    evidence.append(f"52주 고점 대비 {dist_from_high:.1f}%")
                    score += 15
                elif dist_from_low < 5:
                    signals.append("52주 저점 근접")
                    evidence.append(f"52주 저점 대비 {dist_from_low:.1f}%")
                    score += 15

        # Determine status
        if score > 40:
            status = "고위험"
        elif score > 20:
            status = "중위험"
        else:
            status = "저위험"

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
            status="저위험",
            confidence=50.0,
            signals=[],
            evidence=[reason],
            metrics={},
        )
