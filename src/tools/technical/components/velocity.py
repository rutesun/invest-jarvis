import numpy as np
import pandas as pd

from src.tools.technical.context import common_evidence
from src.tools.technical.models import ComponentResult, ComponentSignal


SLOPE_THRESHOLD = 0.05
ACCEL_THRESHOLD = 0.02


def analyze_velocity(df: pd.DataFrame, *, common_analysis=None) -> ComponentResult:
    """Analyze MA slope and acceleration."""
    facts = common_evidence(df, common_analysis, "chart.velocity.legacy")
    if "SMA_20" not in df.columns or len(df) < 15:
        return ComponentResult(
            signals=[],
            evidence=["데이터 부족"],
            metrics={},
            score=0,
        )

    sma_20_series = df["SMA_20"].dropna()
    if len(sma_20_series) < 15:
        return ComponentResult(
            signals=[],
            evidence=["SMA_20 데이터 부족"],
            metrics={},
            score=0,
        )

    if not facts.get("available", False):
        return ComponentResult(signals=[], evidence=["SMA_20 값 0"], metrics={}, score=0)
    current_slope, previous_slope, norm_slope, slope_change, price_above_sma20 = (
        facts[key]
        for key in (
            "current_slope",
            "previous_slope",
            "norm_slope",
            "slope_change",
            "price_above_sma20",
        )
    )

    signals = []
    evidence = []
    score = 0
    metadata = []
    metrics = {
        "norm_slope": round(norm_slope, 4),
        "slope_change": round(slope_change, 4),
    }

    # Direction
    if norm_slope > SLOPE_THRESHOLD:
        evidence.append(f"SMA_20 상승 기울기 ({norm_slope:.4f}%)")
        score += 10

        if slope_change > ACCEL_THRESHOLD:
            signals.append("추세 가속 상승")
            evidence.append(f"기울기 변화율 +{slope_change:.4f}% (가속)")
            score += 10
        elif slope_change < -ACCEL_THRESHOLD * 2:
            signals.append("추세 피로 감지")
            evidence.append(f"기울기 변화율 {slope_change:.4f}% (피로)")
            score -= 5
        elif slope_change < -ACCEL_THRESHOLD:
            signals.append("추세 감속")
            evidence.append(f"기울기 변화율 {slope_change:.4f}% (감속)")

    elif norm_slope < -SLOPE_THRESHOLD and price_above_sma20:
        # 기울기는 하락이나 종가가 SMA20 위 — 지연 신호로 보고 벌점 보류.
        evidence.append(f"SMA_20 하락 기울기이나 종가가 SMA20 위 (지연 신호, {norm_slope:.4f}%)")
    elif norm_slope < -SLOPE_THRESHOLD:
        evidence.append(f"SMA_20 하락 기울기 ({norm_slope:.4f}%)")
        score -= 10

        if slope_change < -ACCEL_THRESHOLD:
            signals.append("하락 가속")
            score -= 10
        elif slope_change > ACCEL_THRESHOLD:
            signals.append("하락 감속")
            score += 5
    else:
        evidence.append(f"SMA_20 횡보 ({norm_slope:.4f}%)")

    # Turning point detection (종가가 SMA20 위면 하락 전환점은 지연 아티팩트라 억제)
    if previous_slope > 0 and current_slope < 0 and not price_above_sma20:
        signals.append("하락 전환점")
        score -= 15
        metadata.append(
            ComponentSignal(
                signal_type="breakdown",
                bias="bearish",
                intent="risk",
                severity="medium",
                source="velocity",
                reason="하락 전환점",
            )
        )
    elif previous_slope < 0 and current_slope > 0:
        signals.append("상승 전환점")
        score += 15
        metadata.append(
            ComponentSignal(
                signal_type="trend",
                bias="bullish",
                intent="hold",
                severity="medium",
                source="velocity",
                reason="상승 전환점",
            )
        )

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
        signal_metadata=metadata,
    )


def _linear_slope(values: np.ndarray) -> float:
    """Calculate linear regression slope."""
    from src.tools.technical.chart_analysis._legacy_components import linear_slope

    return linear_slope(values)
