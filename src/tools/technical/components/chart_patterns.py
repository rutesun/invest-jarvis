# src/tools/technical/components/chart_patterns.py

import pandas as pd
from scipy.signal import find_peaks

from src.tools.technical.models import ChartPatternResult


# Pattern confidence weights (externalized config)
PATTERN_CONFIDENCE_WEIGHTS = {
    "cup_and_handle": {
        "depth_weight": 0.3,
        "handle_weight": 0.3,
        "period_weight": 0.2,
        "volume_weight": 0.2,
    },
}


def detect_cup_and_handle(df: pd.DataFrame) -> ChartPatternResult:
    """Cup & Handle 패턴 감지 (일봉 기준)"""

    if len(df) < 70:
        return ChartPatternResult(
            pattern_name="Cup & Handle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 70일 필요)",
        )

    prices = df["Close"].values

    # Find peaks
    peaks, _ = find_peaks(prices, distance=5, prominence=prices.mean() * 0.05)

    for i in range(1, len(peaks)):
        left_peak_idx = peaks[i - 1]
        right_peak_idx = peaks[i]

        # Cup range
        cup_range = prices[left_peak_idx : right_peak_idx + 1]
        if len(cup_range) < 60 or len(cup_range) > 120:
            continue

        cup_max = max(prices[left_peak_idx], prices[right_peak_idx])
        cup_min = min(cup_range)
        cup_depth = (cup_max - cup_min) / cup_max

        # Validate cup depth (15-40%)
        if not (0.15 <= cup_depth <= 0.40):
            continue

        # Check handle
        handle_range = prices[right_peak_idx : min(right_peak_idx + 10, len(prices))]
        if len(handle_range) < 2:
            continue

        handle_max = handle_range[0]
        handle_min = min(handle_range)
        handle_retracement = (handle_max - handle_min) / handle_max

        # Validate handle (<15%, above cup bottom)
        if handle_retracement <= 0.15 and handle_min > cup_min:
            # Calculate confidence
            confidence = calculate_cup_handle_confidence(
                cup_depth, handle_retracement, len(cup_range)
            )

            # Timing
            completed_idx = right_peak_idx
            completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
            days_ago = len(df) - completed_idx - 1

            # Target price
            target = cup_max + (cup_max - cup_min)

            return ChartPatternResult(
                pattern_name="Cup & Handle",
                detected=True,
                confidence=confidence,
                completed_date=completed_date,
                days_ago=days_ago,
                current_price=prices[-1],
                breakout_level=cup_max,
                support_level=cup_min,
                description=f"컵 깊이 {cup_depth:.1%}, 핸들 조정 {handle_retracement:.1%}, {days_ago}일 전 완성",
                key_levels={
                    "cup_bottom": float(cup_min),
                    "right_peak": float(cup_max),
                    "target": float(target),
                },
            )

    return ChartPatternResult(
        pattern_name="Cup & Handle",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지",
    )


def calculate_cup_handle_confidence(
    cup_depth: float, handle_ret: float, cup_length: int, weights: dict | None = None
) -> float:
    """Cup & Handle confidence scoring"""

    if weights is None:
        weights = PATTERN_CONFIDENCE_WEIGHTS["cup_and_handle"]

    confidence = 0.0

    # 1. Cup depth fit
    ideal_depth = 0.27
    depth_score = 1.0 - abs(cup_depth - ideal_depth) / 0.125
    confidence += depth_score * weights["depth_weight"]

    # 2. Handle retracement fit
    handle_score = 1.0 - (handle_ret / 0.15)
    confidence += handle_score * weights["handle_weight"]

    # 3. Period fit
    if 60 <= cup_length <= 120:
        confidence += weights["period_weight"]

    # 4. Volume (placeholder)
    confidence += 0.5 * weights["volume_weight"]

    return min(confidence, 1.0)
