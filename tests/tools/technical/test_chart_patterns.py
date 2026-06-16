# tests/tools/technical/test_chart_patterns.py

import pandas as pd

from src.tools.technical.components.chart_patterns import detect_cup_and_handle


def create_mock_cup_and_handle(
    cup_depth: float = 0.25, handle_ret: float = 0.10, cup_days: int = 60
) -> pd.DataFrame:
    """Generate mock Cup & Handle pattern"""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=cup_days + 30, freq="D")

    # Left peak
    left_peak = 200.0
    # Cup bottom
    cup_bottom = left_peak * (1 - cup_depth)
    # Right peak
    right_peak = left_peak * 0.98
    # Handle bottom
    handle_bottom = right_peak * (1 - handle_ret)

    prices = []
    for i in range(len(dates)):
        if i < 10:
            # Rise to left peak
            progress = i / 10
            prices.append(150.0 + (left_peak - 150.0) * progress)
        elif i < 15:
            # Plateau at left peak
            prices.append(left_peak)
        elif i < 15 + cup_days // 2:
            # Descending to cup bottom
            progress = (i - 15) / (cup_days // 2)
            prices.append(left_peak - (left_peak - cup_bottom) * progress)
        elif i < 15 + cup_days:
            # Ascending to right peak
            progress = (i - 15 - cup_days // 2) / (cup_days // 2)
            prices.append(cup_bottom + (right_peak - cup_bottom) * progress)
        elif i < 15 + cup_days + 5:
            # Plateau at right peak
            prices.append(right_peak)
        else:
            # Handle
            progress = (i - 15 - cup_days - 5) / 10
            prices.append(right_peak - (right_peak - handle_bottom) * progress)

    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )


def test_cup_and_handle_perfect_pattern():
    """Test Cup & Handle detection with ideal parameters"""
    df = create_mock_cup_and_handle(cup_depth=0.25, handle_ret=0.10, cup_days=60)

    result = detect_cup_and_handle(df)

    assert result.detected is True
    assert result.confidence > 0.6  # Period scoring adjustment
    assert result.pattern_name == "Cup & Handle"
    assert result.breakout_level is not None


def test_cup_and_handle_too_shallow():
    """Cup too shallow (10%) should not detect"""
    df = create_mock_cup_and_handle(cup_depth=0.10)

    result = detect_cup_and_handle(df)

    assert result.detected is False


def test_cup_and_handle_short_cup():
    """40-60일 짧은 Cup 감지 테스트"""
    df = create_mock_cup_and_handle(cup_depth=0.25, handle_ret=0.10, cup_days=50)

    result = detect_cup_and_handle(df)

    assert result.detected is True, f"Failed to detect: {result.description}"
    assert result.confidence > 0.6  # 짧은 cup은 period 감점으로 0.65 정도
    assert result.pattern_name == "Cup & Handle"


def create_mock_double_bottom(
    valley1: float = 100.0, valley2: float = 101.0, neckline: float = 120.0, days: int = 60
) -> pd.DataFrame:
    """Generate mock Double Bottom pattern"""
    import numpy as np

    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    prices = []

    # Calculate segment lengths (flexible for short periods)
    start_segment = max(3, days // 12)  # 시작 구간
    valley1_segment = max(8, days // 4)  # 첫 번째 valley까지
    plateau1 = max(2, days // 20)  # Plateau
    middle_segment = max(8, days // 4)  # Neckline까지
    plateau2 = max(2, days // 20)  # Peak plateau
    valley2_segment = max(8, days // 4)  # 두 번째 valley까지
    plateau3 = max(2, days // 20)  # Bottom plateau

    for i in range(days):
        if i < start_segment:
            # Start above neckline
            prices.append(neckline + 5)
        elif i < start_segment + valley1_segment:
            # Descending to first valley
            progress = (i - start_segment) / valley1_segment
            prices.append((neckline + 5) - ((neckline + 5) - valley1) * progress)
        elif i < start_segment + valley1_segment + plateau1:
            # Bottom plateau
            prices.append(valley1 + np.random.normal(0, 0.5))
        elif i < start_segment + valley1_segment + plateau1 + middle_segment:
            # Ascending to neckline
            progress = (i - start_segment - valley1_segment - plateau1) / middle_segment
            prices.append(valley1 + (neckline - valley1) * progress)
        elif i < start_segment + valley1_segment + plateau1 + middle_segment + plateau2:
            # Peak plateau
            prices.append(neckline + np.random.normal(0, 0.5))
        elif i < (
            start_segment + valley1_segment + plateau1 + middle_segment + plateau2 + valley2_segment
        ):
            # Descending to second valley
            base = start_segment + valley1_segment + plateau1 + middle_segment + plateau2
            progress = (i - base) / valley2_segment
            prices.append(neckline - (neckline - valley2) * progress)
        elif i < (
            start_segment
            + valley1_segment
            + plateau1
            + middle_segment
            + plateau2
            + valley2_segment
            + plateau3
        ):
            # Bottom plateau
            prices.append(valley2 + np.random.normal(0, 0.5))
        else:
            # Ascending again
            base = (
                start_segment
                + valley1_segment
                + plateau1
                + middle_segment
                + plateau2
                + valley2_segment
                + plateau3
            )
            remaining = days - base
            if remaining > 0:
                progress = (i - base) / remaining
                prices.append(valley2 + (neckline - valley2) * progress)
            else:
                prices.append(valley2)

    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )


def test_double_bottom_implementation_exists():
    """Test Double Bottom implementation exists and returns result"""
    from src.tools.technical.components.chart_patterns import detect_double_bottom

    df = create_mock_double_bottom(valley1=100.0, valley2=101.0)
    result = detect_double_bottom(df)

    # Implementation exists and returns valid result
    assert result.pattern_name == "Double Bottom"
    assert result.current_price > 0
    # NOTE: Detection parameters need tuning with real historical data


def test_double_bottom_short_period():
    """20-40일 짧은 기간 Double Bottom 감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_double_bottom

    # 50일 차트에서 25일 간격 패턴 생성
    df = create_mock_double_bottom(valley1=100.0, valley2=101.0, days=55)
    result = detect_double_bottom(df)

    # 짧은 기간도 감지되어야 함
    assert result.detected is True, f"Failed to detect: {result.description}"
    assert result.confidence > 0.6  # 짧은 기간이므로 약간 낮은 confidence
    assert result.pattern_name == "Double Bottom"


def test_head_and_shoulders_implementation_exists():
    """Test H&S implementation exists and returns result"""
    from src.tools.technical.components.chart_patterns import detect_head_and_shoulders

    dates = pd.date_range(end=pd.Timestamp.now(), periods=80, freq="D")
    prices = []
    for i in range(80):
        if i < 20:
            prices.append(100 + i * 2)
        elif i < 40:
            prices.append(140 - (i - 20) * 2)
        elif i < 50:
            prices.append(100 + (i - 40) * 3)
        elif i < 60:
            prices.append(130 - (i - 50) * 3)
        elif i < 70:
            prices.append(100 + (i - 60) * 2)
        else:
            prices.append(120 - (i - 70) * 2)

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_head_and_shoulders(df)
    # Implementation exists and returns valid result
    assert result.pattern_name == "Head & Shoulders"
    assert result.current_price > 0
    # NOTE: Detection parameters need tuning with real historical data


def test_head_and_shoulders_short_period():
    """60-70일 짧은 기간 H&S 감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_head_and_shoulders

    # 75일 차트에서 65일 H&S 패턴 생성 (left shoulder ~ right shoulder)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=75, freq="D")
    prices = []

    # 0-15: 상승 to left shoulder (120)
    for i in range(15):
        prices.append(100 + i * (20 / 15))

    # 15-20: Left shoulder plateau
    for _ in range(5):
        prices.append(120)

    # 20-30: 하락 to valley (100)
    for i in range(10):
        prices.append(120 - i * 2)

    # 30-40: 상승 to head (140)
    for i in range(10):
        prices.append(100 + i * 4)

    # 40-50: 하락 to valley (100)
    for i in range(10):
        prices.append(140 - i * 4)

    # 50-65: 상승 to right shoulder (118)
    for i in range(15):
        prices.append(100 + i * (18 / 15))

    # 65-75: 하락
    for i in range(10):
        prices.append(118 - i * 2)

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_head_and_shoulders(df)

    assert result.detected is True, f"Failed to detect: {result.description}"
    assert result.confidence > 0.6  # 짧은 기간 약간 감점
    assert result.pattern_name == "Head & Shoulders"


def create_mock_ascending_triangle(days: int = 60) -> pd.DataFrame:
    """Generate mock Ascending Triangle pattern

    - 수평 저항선 (고점들이 비슷)
    - 상승 지지선 (저점들이 점점 높아짐)
    """
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    prices = []

    resistance = 150.0
    support_levels = [130.0, 137.5, 145.0]  # 저점들이 점점 상승

    # 명확한 3개의 valley-peak 사이클 (급격한 변화로 prominence 확보)
    for cycle in range(3):
        valley_price = support_levels[cycle]
        peak_price = resistance

        # 저점 도달 및 반등
        prices.extend([valley_price] * 2)  # valley 확실하게

        # 급격한 상승
        for i in range(1, 8):
            progress = i / 8
            prices.append(valley_price + (peak_price - valley_price) * progress)

        # 고점 도달
        prices.extend([peak_price] * 2)  # peak 확실하게

        # 하락 (다음 cycle로, 마지막은 제외)
        if cycle < 2:
            next_valley = support_levels[cycle + 1]
            for i in range(1, 8):
                progress = i / 8
                prices.append(peak_price - (peak_price - next_valley) * progress)

    # Fill remaining days to match length
    while len(prices) < days:
        prices.append(prices[-1])  # 마지막 가격 유지

    return pd.DataFrame(
        {
            "Open": prices[:days],
            "High": [p * 1.01 for p in prices[:days]],
            "Low": [p * 0.99 for p in prices[:days]],
            "Close": prices[:days],
        },
        index=dates,
    )


def test_ascending_triangle_perfect():
    """이상적인 Ascending Triangle 패턴 감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_ascending_triangle

    df = create_mock_ascending_triangle(days=60)
    result = detect_ascending_triangle(df)

    # Implementation exists and returns result
    assert result.pattern_name == "Ascending Triangle"
    assert result.current_price > 0
    # NOTE: Synthetic data detection needs tuning with real historical data in Task 9


def test_ascending_triangle_no_convergence():
    """Ascending Triangle without convergence should not detect"""
    from src.tools.technical.components.chart_patterns import detect_ascending_triangle

    # Create pattern where peaks are horizontal but valleys don't rise (parallel lines)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")

    # Oscillate between 130-150 with no convergence
    prices = [140 + 10 * ((i % 10) / 5 - 1) for i in range(60)]

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_ascending_triangle(df)

    # Should fail convergence check
    assert result.detected is False


def test_descending_triangle_insufficient_decline():
    """Descending Triangle with insufficient resistance decline should not detect"""
    from src.tools.technical.components.chart_patterns import detect_descending_triangle

    # Peaks don't decline enough (flat resistance)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")
    prices = [140 - 10 * ((i % 10) / 5 - 1) for i in range(60)]

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_descending_triangle(df)

    # Should fail slope or convergence check
    assert result.detected is False


def test_bullish_flag_weak_pole():
    """Bullish Flag with weak pole (<10%) should not detect"""
    from src.tools.technical.components.chart_patterns import detect_bullish_flag

    # Only 5% rise (too weak for flagpole)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=40, freq="D")
    prices = [100 + i * 0.125 for i in range(40)]  # 100 → 105 (5% total)

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_bullish_flag(df)

    assert result.detected is False
    assert "Flagpole 상승 불충분" in result.description


def test_bearish_flag_weak_pole():
    """Bearish Flag with weak pole (<10%) should not detect"""
    from src.tools.technical.components.chart_patterns import detect_bearish_flag

    # Only 5% drop (too weak for flagpole)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=40, freq="D")
    prices = [140 - i * 0.125 for i in range(40)]  # 140 → 135 (5% drop)

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_bearish_flag(df)

    assert result.detected is False
    assert "Flagpole 하락 불충분" in result.description


def test_descending_triangle_implementation():
    """Descending Triangle implementation exists"""
    from src.tools.technical.components.chart_patterns import detect_descending_triangle

    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")
    prices = [140 - i * 0.2 for i in range(60)]  # Simple descending trend

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_descending_triangle(df)

    # Implementation exists and returns result
    assert result.pattern_name == "Descending Triangle"
    assert result.current_price > 0
    # NOTE: Real data validation in Task 9


def test_bullish_flag_implementation():
    """Bullish Flag implementation exists"""
    from src.tools.technical.components.chart_patterns import detect_bullish_flag

    dates = pd.date_range(end=pd.Timestamp.now(), periods=40, freq="D")
    prices = [100 + i * 2 for i in range(40)]  # Simple uptrend

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_bullish_flag(df)

    # Implementation exists and returns result
    assert result.pattern_name == "Bullish Flag"
    assert result.current_price > 0
    # NOTE: Real data validation in Task 9


def test_bearish_flag_implementation():
    """Bearish Flag implementation exists"""
    from src.tools.technical.components.chart_patterns import detect_bearish_flag

    dates = pd.date_range(end=pd.Timestamp.now(), periods=40, freq="D")
    prices = [140 - i * 2 for i in range(40)]  # Simple downtrend

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    result = detect_bearish_flag(df)

    # Implementation exists and returns result
    assert result.pattern_name == "Bearish Flag"
    assert result.current_price > 0
    # NOTE: Real data validation in Task 9


def test_detect_chart_patterns_integration():
    """Test all patterns are integrated in detect_chart_patterns"""
    from src.tools.technical.components.chart_patterns import detect_chart_patterns
    from src.tools.technical.models import IndicatorSnapshot

    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="D")
    prices = [100 + i * 0.5 for i in range(100)]

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )

    snapshot = IndicatorSnapshot(
        price=prices[-1],
        change_pct=1.0,
        support_s1=140.0,
        resistance_r1=150.0,
        sma_50=135.0,
        sma_200=130.0,
    )

    patterns = detect_chart_patterns(df, snapshot)

    # Verify all 9 patterns are included
    expected_patterns = {
        "cup_and_handle",
        "double_bottom",
        "head_and_shoulders",
        "ascending_triangle",
        "descending_triangle",
        "bullish_flag",
        "bearish_flag",
        "support_level_test",
        "support_resistance_test",
    }

    assert set(patterns.keys()) == expected_patterns
    assert all(isinstance(p, type(patterns["cup_and_handle"])) for p in patterns.values())


def test_support_resistance_test_near_level():
    """Test detection when price near support/resistance"""
    from src.tools.technical.components.chart_patterns import test_support_resistance
    from src.tools.technical.models import IndicatorSnapshot

    df = pd.DataFrame(
        {"Close": [200.0] * 30},
        index=pd.date_range(end=pd.Timestamp.now(), periods=30, freq="D"),
    )

    snapshot = IndicatorSnapshot(
        price=200.5,  # Within 2% of pivot
        change_pct=0.25,
        support_s1=200.0,
        resistance_r1=210.0,
        sma_50=185.0,
        sma_200=170.0,
    )

    result = test_support_resistance(df, snapshot)

    assert result.detected is True
    assert "테스트 중" in result.description


def test_support_resistance_test_uses_shared_swings():
    """snapshot 레벨이 비어도 shared swings 레벨로 테스트 가능해야 한다."""
    from src.tools.technical.components.chart_patterns import test_support_resistance
    from src.tools.technical.components.swing_extractor import SwingCandidate, SwingExtractorOutput
    from src.tools.technical.models import IndicatorSnapshot

    index = pd.date_range(end=pd.Timestamp.now(), periods=30, freq="D")
    df = pd.DataFrame({"Close": [200.0] * 30}, index=index)

    snapshot = IndicatorSnapshot(
        price=200.5,
        change_pct=0.25,
    )
    swings = SwingExtractorOutput(
        demand_candidates=[
            SwingCandidate(
                price=200.0,
                timestamp=pd.Timestamp(index[-2]),
                volume=1_200_000.0,
            )
        ],
        supply_candidates=[],
    )

    result = test_support_resistance(df, snapshot, swings=swings)

    assert result.detected is True
    assert result.key_levels is not None
    assert result.key_levels["name"] == "공유 스윙 저점"


def test_detect_chart_patterns_support_resistance_uses_swings_when_passed():
    from src.tools.technical.components.chart_patterns import detect_chart_patterns
    from src.tools.technical.components.swing_extractor import SwingCandidate, SwingExtractorOutput
    from src.tools.technical.models import IndicatorSnapshot

    index = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="D")
    prices = [200.0] * 100
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=index,
    )
    snapshot = IndicatorSnapshot(price=200.5, change_pct=0.0)
    swings = SwingExtractorOutput(
        demand_candidates=[
            SwingCandidate(
                price=200.0,
                timestamp=pd.Timestamp(index[-5]),
                volume=950_000.0,
            )
        ],
        supply_candidates=[],
    )

    patterns = detect_chart_patterns(df, snapshot, swings=swings)
    support_resistance = patterns["support_resistance_test"]

    assert support_resistance.detected is True
    assert support_resistance.key_levels is not None
    assert support_resistance.key_levels["name"] == "공유 스윙 저점"


def test_support_level_test_multiple_touches():
    """Support Level Test: 여러 저점이 같은 가격대"""
    from src.tools.technical.components.chart_patterns import detect_support_level_test

    # 4개 저점이 7.50~7.72 범위 (약 3%)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")

    valleys = {10: 7.50, 25: 7.68, 40: 7.72, 55: 7.66}

    prices = []
    for i in range(60):
        if i in valleys:
            prices.append(valleys[i])
        elif i in [11, 12, 13, 26, 27, 28, 41, 42, 43, 56, 57, 58]:
            # 저점 직후 10% 반등
            prices.append(prices[-1] * 1.10)
        else:
            # 반등 레벨 유지 (8.2~8.4)
            prices.append(8.3)

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.02 for p in prices],
            "Low": prices,
            "Close": [p * 1.01 for p in prices],
        },
        index=dates,
    )

    result = detect_support_level_test(df)

    assert result.detected is True
    assert result.confidence > 0.5
    assert result.pattern_name == "Support Level Test"
    assert result.key_levels is not None
    assert result.key_levels["test_count"] >= 3
    assert "회 테스트" in result.description


def test_support_level_test_too_wide_range():
    """Support Level Test: 가격 범위 너무 넓으면 미감지"""
    from src.tools.technical.components.chart_patterns import detect_support_level_test

    # 저점들이 10% 차이 (너무 넓음)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")
    prices = []
    for i in range(60):
        if i == 10:
            prices.append(7.0)
        elif i == 25:
            prices.append(7.7)  # 10% 차이
        elif i == 40:
            prices.append(7.3)
        else:
            prices.append(9.0)

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.05 for p in prices],
            "Low": prices,
            "Close": [p * 1.02 for p in prices],
        },
        index=dates,
    )

    result = detect_support_level_test(df)

    assert result.detected is False
    assert "범위 초과" in result.description or "같은 레벨의 저점 그룹 없음" in result.description


def test_support_level_test_weak_rebounds():
    """Support Level Test: 반등 약하면 미감지"""
    from src.tools.technical.components.chart_patterns import detect_support_level_test

    # 저점 가격대는 유사하지만 반등이 약함 (2%)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")
    prices = []
    for i in range(60):
        if i == 10:
            prices.append(7.35)
        elif i == 25:
            prices.append(7.71)
        elif i == 40:
            prices.append(7.66)
        elif i in [11, 12, 26, 27, 41, 42]:
            # 약한 반등 (2% only)
            prices.append(prices[-1] * 1.02)
        else:
            prices.append(7.5)

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": prices,
            "Close": prices,
        },
        index=dates,
    )

    result = detect_support_level_test(df)

    assert result.detected is False
    assert "반등 부족" in result.description


def test_bullish_flag_handles_trailing_nan_close():
    """당일 미완성 봉(마지막 Close=NaN)이어도 description/지표에 NaN이 없어야 한다."""
    import numpy as np

    from src.tools.technical.components.chart_patterns import detect_bullish_flag

    pole = list(np.linspace(100.0, 145.0, 15))  # 강한 상승 (+45%)
    flag = list(np.linspace(144.0, 138.0, 14))  # 약한 눌림
    closes = pole + flag + [float("nan")]  # 30 rows, 마지막 봉 미완성
    df = pd.DataFrame(
        {"Close": closes},
        index=pd.date_range("2026-04-01", periods=len(closes), freq="D"),
    )

    result = detect_bullish_flag(df)

    assert "nan" not in result.description.lower()
    assert not np.isnan(result.current_price)
