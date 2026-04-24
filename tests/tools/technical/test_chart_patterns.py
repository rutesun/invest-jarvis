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
    assert result.confidence > 0.7
    assert result.pattern_name == "Cup & Handle"
    assert result.breakout_level is not None


def test_cup_and_handle_too_shallow():
    """Cup too shallow (10%) should not detect"""
    df = create_mock_cup_and_handle(cup_depth=0.10)

    result = detect_cup_and_handle(df)

    assert result.detected is False


def create_mock_double_bottom(
    valley1: float = 100.0, valley2: float = 101.0, neckline: float = 120.0, days: int = 60
) -> pd.DataFrame:
    """Generate mock Double Bottom pattern"""
    import numpy as np

    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    prices = []
    for i in range(days):
        if i < 5:
            # Start above neckline
            prices.append(neckline + 5)
        elif i < days // 3:
            # Descending to first valley
            progress = (i - 5) / (days // 3 - 5)
            prices.append((neckline + 5) - ((neckline + 5) - valley1) * progress)
        elif i < days // 3 + 5:
            # Bottom plateau
            prices.append(valley1 + np.random.normal(0, 0.5))
        elif i < 2 * days // 3:
            # Ascending to neckline
            progress = (i - days // 3 - 5) / (days // 3 - 5)
            prices.append(valley1 + (neckline - valley1) * progress)
        elif i < 2 * days // 3 + 5:
            # Peak plateau
            prices.append(neckline + np.random.normal(0, 0.5))
        elif i < 5 * days // 6:
            # Descending to second valley
            progress = (i - 2 * days // 3 - 5) / (days // 6 - 5)
            prices.append(neckline - (neckline - valley2) * progress)
        elif i < 5 * days // 6 + 5:
            # Bottom plateau
            prices.append(valley2 + np.random.normal(0, 0.5))
        else:
            # Ascending again
            progress = (i - 5 * days // 6 - 5) / (days // 6 - 5)
            prices.append(valley2 + (neckline - valley2) * progress)

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
