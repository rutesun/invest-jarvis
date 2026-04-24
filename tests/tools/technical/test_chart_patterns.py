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
