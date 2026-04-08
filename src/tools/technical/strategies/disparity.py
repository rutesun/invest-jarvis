import pandas as pd
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class DisparityStrategy(BaseStrategy):
    """이격도 기반 과열/침체 분석."""

    name = "disparity"
    description = "20/50/120일 이격도 기반 과열/침체 분석"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if df.empty or len(df) < 120:
            return self._neutral_result("데이터 부족")

        latest = df.iloc[-1]
        signals = []
        evidence = []
        metrics = {}
        score = 0

        # Analyze 20-day disparity
        disp_20 = self._safe_get(latest, "Disparity_20")
        if disp_20:
            metrics["disparity_20"] = round(disp_20, 2)
            if disp_20 > 110:
                signals.append("20일 이격도 과열")
                evidence.append(f"20일 이격도 {disp_20:.1f}% (>110%)")
                score -= 20
            elif disp_20 < 90:
                signals.append("20일 이격도 침체")
                evidence.append(f"20일 이격도 {disp_20:.1f}% (<90%)")
                score += 20
            else:
                evidence.append(f"20일 이격도 {disp_20:.1f}% (정상권)")

        # Analyze 50-day disparity
        disp_50 = self._safe_get(latest, "Disparity_50")
        if disp_50:
            metrics["disparity_50"] = round(disp_50, 2)
            if disp_50 > 110:
                signals.append("50일 이격도 과열")
                evidence.append(f"50일 이격도 {disp_50:.1f}% (>110%)")
                score -= 15
            elif disp_50 < 90:
                signals.append("50일 이격도 침체")
                evidence.append(f"50일 이격도 {disp_50:.1f}% (<90%)")
                score += 15
            else:
                evidence.append(f"50일 이격도 {disp_50:.1f}% (정상권)")

        # Analyze 120-day disparity
        disp_120 = self._safe_get(latest, "Disparity_120")
        if disp_120:
            metrics["disparity_120"] = round(disp_120, 2)
            if disp_120 > 110:
                signals.append("120일 이격도 과열")
                evidence.append(f"120일 이격도 {disp_120:.1f}% (>110%)")
                score -= 10
            elif disp_120 < 90:
                signals.append("120일 이격도 침체")
                evidence.append(f"120일 이격도 {disp_120:.1f}% (<90%)")
                score += 10
            else:
                evidence.append(f"120일 이격도 {disp_120:.1f}% (정상권)")

        # Determine status
        if score > 30:
            status = "침체"
        elif score < -30:
            status = "과열"
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
