# src/tools/technical/components/chart_patterns.py

import pandas as pd
from scipy.signal import find_peaks

from src.tools.technical.models import ChartPatternResult, IndicatorSnapshot


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

    # 최소 데이터 요구사항 완화: 70일 → 50일
    if len(df) < 50:
        return ChartPatternResult(
            pattern_name="Cup & Handle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 50일 필요)",
        )

    prices = df["Close"].values

    # Find peaks
    peaks, _ = find_peaks(prices, distance=5, prominence=prices.mean() * 0.05)

    for i in range(1, len(peaks)):
        left_peak_idx = peaks[i - 1]
        right_peak_idx = peaks[i]

        # Cup range (Cup 길이 제약 완화: 60-120일 → 40-120일)
        cup_range = prices[left_peak_idx : right_peak_idx + 1]
        if len(cup_range) < 40 or len(cup_range) > 120:
            continue

        cup_max = max(prices[left_peak_idx], prices[right_peak_idx])
        cup_min = min(cup_range)
        cup_depth = (cup_max - cup_min) / cup_max

        # Validate cup depth (15-40%)
        if not (0.15 <= cup_depth <= 0.40):
            continue

        # Check handle (Handle 길이 확장: max 10일 → max 20일)
        handle_range = prices[right_peak_idx : min(right_peak_idx + 20, len(prices))]
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

    # 3. Period fit (거리에 따라 차등 점수)
    if 60 <= cup_length <= 120:
        period_score = 1.0
    elif 40 <= cup_length < 60:
        period_score = 0.9  # 짧은 cup 약간 감점
    else:
        period_score = 0.7
    confidence += period_score * weights["period_weight"]

    # 4. Volume (placeholder)
    confidence += 0.5 * weights["volume_weight"]

    return min(confidence, 1.0)


def detect_double_bottom(df: pd.DataFrame) -> ChartPatternResult:
    """Double Bottom 패턴 감지 (일봉)"""

    if len(df) < 50:
        return ChartPatternResult(
            pattern_name="Double Bottom",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 50일 필요)",
        )

    prices = df["Close"].values

    # Find valleys (inverted peaks) - prominence 완화: 0.03 → 0.02
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.02)

    for i in range(1, len(valleys)):
        valley1_idx = valleys[i - 1]
        valley2_idx = valleys[i]

        # Distance 제약 완화: 40-80일 → 20-80일
        if valley2_idx - valley1_idx < 20 or valley2_idx - valley1_idx > 80:
            continue

        bottom1 = prices[valley1_idx]
        bottom2 = prices[valley2_idx]

        # Check valley height similarity (<5%)
        height_diff = abs(bottom1 - bottom2) / min(bottom1, bottom2)
        if height_diff > 0.05:
            continue

        # Find neckline (middle peak)
        middle_range = prices[valley1_idx:valley2_idx]
        neckline = max(middle_range)

        # Validate rebound (>10%)
        rebound = (neckline - min(bottom1, bottom2)) / min(bottom1, bottom2)
        if rebound < 0.10:
            continue

        # Confidence (distance 파라미터 추가)
        distance = valley2_idx - valley1_idx
        confidence = calculate_double_bottom_confidence(height_diff, rebound, distance)

        # Timing
        completed_idx = valley2_idx
        completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
        days_ago = len(df) - completed_idx - 1

        # Target
        target = neckline + (neckline - min(bottom1, bottom2))

        return ChartPatternResult(
            pattern_name="Double Bottom",
            detected=True,
            confidence=confidence,
            completed_date=completed_date,
            days_ago=days_ago,
            current_price=prices[-1],
            breakout_level=neckline,
            support_level=min(bottom1, bottom2),
            description=f"두 저점 높이 차이 {height_diff:.1%}, {days_ago}일 전 완성",
            key_levels={
                "bottom1": float(bottom1),
                "bottom2": float(bottom2),
                "neckline": float(neckline),
                "target": float(target),
            },
        )

    return ChartPatternResult(
        pattern_name="Double Bottom",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지",
    )


def calculate_double_bottom_confidence(height_diff: float, rebound: float, distance: int) -> float:
    """Double Bottom confidence scoring"""
    confidence = 0.0

    # 1. Valley similarity (0-0.4)
    similarity_score = 1.0 - (height_diff / 0.05)
    confidence += similarity_score * 0.4

    # 2. Rebound strength (0-0.3)
    rebound_score = min(rebound / 0.20, 1.0)
    confidence += rebound_score * 0.3

    # 3. Period fit (0-0.3) - 거리에 따라 차등 점수
    if 40 <= distance <= 60:
        period_score = 1.0
    elif 20 <= distance < 40:
        period_score = 0.85  # 짧은 기간 약간 감점
    elif 60 < distance <= 80:
        period_score = 0.95
    else:
        period_score = 0.5
    confidence += period_score * 0.3

    return min(confidence, 1.0)


def detect_head_and_shoulders(df: pd.DataFrame) -> ChartPatternResult:
    """Head & Shoulders 패턴 감지 (일봉)"""

    if len(df) < 50:
        return ChartPatternResult(
            pattern_name="Head & Shoulders",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 50일 필요)",
        )

    prices = df["Close"].values

    # Find 3 peaks (distance 증가로 노이즈 필터링)
    peaks, _ = find_peaks(prices, distance=15, prominence=prices.mean() * 0.05)

    if len(peaks) < 3:
        return ChartPatternResult(
            pattern_name="Head & Shoulders",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description="고점 부족 (3개 필요)",
        )

    for i in range(len(peaks) - 2):
        left_shoulder_idx = peaks[i]
        head_idx = peaks[i + 1]
        right_shoulder_idx = peaks[i + 2]

        if (
            right_shoulder_idx - left_shoulder_idx < 40
            or right_shoulder_idx - left_shoulder_idx > 100
        ):
            continue

        left_shoulder = prices[left_shoulder_idx]
        head = prices[head_idx]
        right_shoulder = prices[right_shoulder_idx]

        # Head must be higher (>3%)
        if head <= left_shoulder * 1.03 or head <= right_shoulder * 1.03:
            continue

        # Shoulders similar height (<10%)
        shoulder_diff = abs(left_shoulder - right_shoulder) / max(left_shoulder, right_shoulder)
        if shoulder_diff > 0.10:
            continue

        # Neckline
        left_valley = prices[left_shoulder_idx:head_idx].min()
        right_valley = prices[head_idx:right_shoulder_idx].min()
        neckline = (left_valley + right_valley) / 2

        # Confidence
        head_prominence = (head - max(left_shoulder, right_shoulder)) / head
        confidence = calculate_head_shoulders_confidence(head_prominence, shoulder_diff)

        # Timing
        completed_idx = right_shoulder_idx
        completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
        days_ago = len(df) - completed_idx - 1

        # Target (downward)
        target = neckline - (head - neckline)

        return ChartPatternResult(
            pattern_name="Head & Shoulders",
            detected=True,
            confidence=confidence,
            completed_date=completed_date,
            days_ago=days_ago,
            current_price=prices[-1],
            breakout_level=neckline,
            support_level=target,
            description=f"헤드-어깨 높이 차이 {head_prominence:.1%}, {days_ago}일 전 완성",
            key_levels={
                "left_shoulder": float(left_shoulder),
                "head": float(head),
                "right_shoulder": float(right_shoulder),
                "neckline": float(neckline),
                "target": float(target),
            },
        )

    return ChartPatternResult(
        pattern_name="Head & Shoulders",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지",
    )


def calculate_head_shoulders_confidence(head_prominence: float, shoulder_diff: float) -> float:
    """H&S confidence scoring"""
    confidence = 0.0

    # Head prominence
    prominence_score = min(head_prominence / 0.10, 1.0)
    confidence += prominence_score * 0.4

    # Shoulder similarity
    similarity_score = 1.0 - (shoulder_diff / 0.10)
    confidence += similarity_score * 0.3

    # Period fit
    confidence += 0.3

    return min(confidence, 1.0)


def test_support_resistance(df: pd.DataFrame, snapshot: IndicatorSnapshot) -> ChartPatternResult:
    """현재가가 주요 레벨 근처(±2%)에 있는지 테스트"""

    current_price = snapshot.price
    levels = []

    # Collect levels
    if snapshot.support_s1:
        levels.append(("support", snapshot.support_s1, "피봇 S1"))
    if snapshot.resistance_r1:
        levels.append(("resistance", snapshot.resistance_r1, "피봇 R1"))
    if snapshot.sma_50:
        levels.append(("support", snapshot.sma_50, "50일선"))
    if snapshot.sma_200:
        levels.append(("support", snapshot.sma_200, "200일선"))
    if snapshot.swing_high:
        levels.append(("resistance", snapshot.swing_high, "스윙 고점"))
    if snapshot.swing_low:
        levels.append(("support", snapshot.swing_low, "스윙 저점"))

    # Check ±2% proximity
    for level_type, level_price, level_name in levels:
        distance_pct = abs(current_price - level_price) / current_price

        if distance_pct <= 0.02:
            return ChartPatternResult(
                pattern_name="Support/Resistance Test",
                detected=True,
                confidence=1.0 - distance_pct / 0.02,
                completed_date=df.index[-1].strftime("%Y-%m-%d"),
                days_ago=0,
                current_price=current_price,
                breakout_level=level_price if level_type == "resistance" else None,
                support_level=level_price if level_type == "support" else None,
                description=f"{level_name} 테스트 중 (거리 {distance_pct:.1%})",
                key_levels={
                    "test_level": float(level_price),
                    "type": level_type,
                    "name": level_name,
                },
            )

    return ChartPatternResult(
        pattern_name="Support/Resistance Test",
        detected=False,
        confidence=0.0,
        current_price=current_price,
        description="레벨 근처 아님",
    )


def detect_ascending_triangle(df: pd.DataFrame) -> ChartPatternResult:
    """Ascending Triangle 패턴 감지

    수평 저항선 + 상승 지지선, 돌파 시 상승 기대
    """
    if len(df) < 40:
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 40일 필요)",
        )

    import numpy as np
    from scipy.stats import linregress

    prices = df["Close"].values

    # 고점/저점 추출
    peaks, _ = find_peaks(prices, distance=10, prominence=prices.mean() * 0.03)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.03)

    if len(peaks) < 3 or len(valleys) < 3:
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description="고점/저점 부족 (각 3개 필요)",
        )

    # 최근 3-4개 고점/저점만 사용
    recent_peaks = peaks[-4:] if len(peaks) >= 4 else peaks[-3:]
    recent_valleys = valleys[-4:] if len(valleys) >= 4 else valleys[-3:]

    # 패턴 기간 확인
    pattern_start = min(recent_peaks[0], recent_valleys[0])
    pattern_end = max(recent_peaks[-1], recent_valleys[-1])
    pattern_length = pattern_end - pattern_start

    if not (30 <= pattern_length <= 90):
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"패턴 기간 부적합 ({pattern_length}일, 30-90일 필요)",
        )

    # 고점 수평성 확인
    peak_prices = prices[recent_peaks]
    peak_std = np.std(peak_prices) / np.mean(peak_prices)

    if peak_std > 0.03:  # 표준편차 >3%면 수평 아님
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"고점 수평성 부족 (std: {peak_std:.2%} > 3%)",
        )

    # 저점 상승 추세 확인 (선형회귀)
    valley_prices = prices[recent_valleys]
    slope, intercept, r_value, _, _ = linregress(recent_valleys, valley_prices)

    daily_slope = slope / pattern_length

    if daily_slope <= 0.001:  # 일일 0.1% 미만 상승이면 불충분
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"저점 상승 추세 불충분 (기울기: {daily_slope * 100:.3%}/day)",
        )

    # 수렴 확인
    first_gap = peak_prices[0] - valley_prices[0]
    last_gap = peak_prices[-1] - valley_prices[-1]

    if last_gap > first_gap * 0.5:  # 간격이 50% 이하로 좁아지지 않음
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"수렴 부족 (gap: {last_gap / first_gap:.1%})",
        )

    # Confidence 계산
    resistance_level = np.mean(peak_prices)
    support_slope_percent = daily_slope * 100
    convergence_ratio = last_gap / first_gap

    confidence = calculate_triangle_confidence(
        peak_std, support_slope_percent, convergence_ratio, "ascending"
    )

    # Target price: resistance + (resistance - first valley)
    target = resistance_level + (resistance_level - valley_prices[0])

    # Timing
    completed_date = df.index[pattern_end].strftime("%Y-%m-%d")
    days_ago = len(df) - pattern_end - 1

    return ChartPatternResult(
        pattern_name="Ascending Triangle",
        detected=True,
        confidence=confidence,
        completed_date=completed_date,
        days_ago=days_ago,
        current_price=prices[-1],
        breakout_level=resistance_level,
        support_level=valley_prices[-1],
        description=f"고점 수평도 {peak_std:.2%}, 저점 기울기 +{support_slope_percent:.2%}/day, {pattern_length}일",
        key_levels={
            "resistance": float(resistance_level),
            "support_start": float(valley_prices[0]),
            "support_end": float(valley_prices[-1]),
            "target": float(target),
        },
    )


def calculate_triangle_confidence(
    peak_std: float,
    slope_percent: float,
    convergence_ratio: float,
    triangle_type: str,  # "ascending" or "descending"
) -> float:
    """Triangle 패턴 confidence scoring

    Args:
        peak_std: 수평선 표준편차 (ascending은 고점, descending은 저점)
        slope_percent: 추세선 기울기 (일일 %)
        convergence_ratio: 마지막/첫 gap 비율 (작을수록 수렴)
        triangle_type: 패턴 타입
    """
    confidence = 0.0

    # 1. 수평선 품질 (0-0.4)
    horizontal_score = max(0, 1.0 - peak_std / 0.03)
    confidence += horizontal_score * 0.4

    # 2. 추세선 기울기 (0-0.3)
    # Ideal: 0.15% per day
    ideal_slope = 0.15
    slope_score = max(0, 1.0 - abs(abs(slope_percent) - ideal_slope) / 0.15)
    confidence += slope_score * 0.3

    # 3. 수렴도 (0-0.3)
    # 작을수록 좋음 (0이면 완전 수렴)
    convergence_score = 1.0 - convergence_ratio
    confidence += convergence_score * 0.3

    return min(confidence, 1.0)


def detect_descending_triangle(df: pd.DataFrame) -> ChartPatternResult:
    """Descending Triangle 패턴 감지

    하락 저항선 + 수평 지지선, 하락 돌파 시 추가 하락 기대
    """
    if len(df) < 40:
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 40일 필요)",
        )

    import numpy as np
    from scipy.stats import linregress

    prices = df["Close"].values

    # 고점/저점 추출
    peaks, _ = find_peaks(prices, distance=10, prominence=prices.mean() * 0.03)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.03)

    if len(peaks) < 3 or len(valleys) < 3:
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description="고점/저점 부족 (각 3개 필요)",
        )

    # 최근 3-4개 고점/저점만 사용
    recent_peaks = peaks[-4:] if len(peaks) >= 4 else peaks[-3:]
    recent_valleys = valleys[-4:] if len(valleys) >= 4 else valleys[-3:]

    # 패턴 기간 확인
    pattern_start = min(recent_peaks[0], recent_valleys[0])
    pattern_end = max(recent_peaks[-1], recent_valleys[-1])
    pattern_length = pattern_end - pattern_start

    if not (30 <= pattern_length <= 90):
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"패턴 기간 부적합 ({pattern_length}일, 30-90일 필요)",
        )

    # 저점 수평성 확인
    valley_prices = prices[recent_valleys]
    valley_std = np.std(valley_prices) / np.mean(valley_prices)

    if valley_std > 0.03:  # 표준편차 >3%면 수평 아님
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"저점 수평성 부족 (std: {valley_std:.2%} > 3%)",
        )

    # 고점 하락 추세 확인 (선형회귀)
    peak_prices = prices[recent_peaks]
    slope, intercept, r_value, _, _ = linregress(recent_peaks, peak_prices)

    daily_slope = slope / pattern_length

    if daily_slope >= -0.001:  # 일일 0.1% 미만 하락이면 불충분
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"고점 하락 추세 불충분 (기울기: {daily_slope * 100:.3%}/day)",
        )

    # 수렴 확인
    first_gap = peak_prices[0] - valley_prices[0]
    last_gap = peak_prices[-1] - valley_prices[-1]

    if last_gap > first_gap * 0.5:  # 간격이 50% 이하로 좁아지지 않음
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"수렴 부족 (gap: {last_gap / first_gap:.1%})",
        )

    # Confidence 계산
    support_level = np.mean(valley_prices)
    resistance_slope_percent = abs(daily_slope * 100)
    convergence_ratio = last_gap / first_gap

    confidence = calculate_triangle_confidence(
        valley_std, resistance_slope_percent, convergence_ratio, "descending"
    )

    # Target price: support - (first peak - support)
    target = support_level - (peak_prices[0] - support_level)

    # Timing
    completed_date = df.index[pattern_end].strftime("%Y-%m-%d")
    days_ago = len(df) - pattern_end - 1

    return ChartPatternResult(
        pattern_name="Descending Triangle",
        detected=True,
        confidence=confidence,
        completed_date=completed_date,
        days_ago=days_ago,
        current_price=prices[-1],
        breakout_level=support_level,  # 하락 돌파 예상
        support_level=target,  # 목표가 (하락)
        description=f"저점 수평도 {valley_std:.2%}, 고점 기울기 -{resistance_slope_percent:.2%}/day, {pattern_length}일",
        key_levels={
            "support": float(support_level),
            "resistance_start": float(peak_prices[0]),
            "resistance_end": float(peak_prices[-1]),
            "target": float(target),
        },
    )


def detect_chart_patterns(
    df: pd.DataFrame, snapshot: IndicatorSnapshot | None = None
) -> dict[str, ChartPatternResult]:
    """모든 차트 패턴 감지 통합 함수"""

    patterns = {
        "cup_and_handle": detect_cup_and_handle(df),
        "double_bottom": detect_double_bottom(df),
        "head_and_shoulders": detect_head_and_shoulders(df),
    }

    if snapshot:
        patterns["support_resistance_test"] = test_support_resistance(df, snapshot)

    return patterns
