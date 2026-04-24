import numpy as np
import pandas as pd
import pytest

from src.tools.technical.components.volume import analyze_volume
from src.tools.technical.indicators import IndicatorCalculator


@pytest.fixture
def volume_spike_df():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.3
    volume = [1000000] * 99 + [5000000]  # spike on last day
    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_volume_spike(volume_spike_df):
    result = analyze_volume(volume_spike_df)
    assert any("급증" in s for s in result.signals)
    assert result.metrics.get("vol_ratio", 0) > 2.0


def test_volume_no_data():
    df = pd.DataFrame({"Close": [100], "Volume": [1000]})
    result = analyze_volume(df)
    assert result.score == 0


def test_pocket_pivot_detected():
    """Pocket Pivot: Down-day volume exceeds max of last 10 down-days, near 50MA."""
    # Create 60 days of data for 50MA calculation
    # Days 0-49: mixed up/down days with normal volume
    # Day 50-58: down days with volume 800k, 700k, 600k, ..., 200k
    # Day 59: down day with volume 1M (exceeds all previous down-day volumes)

    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    close_values = [100.0] * 50 + [99, 98, 97, 96, 95, 94, 93, 92, 91, 90]  # Last 10 days declining
    open_values = [100.5] * 50 + [100, 99, 98, 97, 96, 95, 94, 93, 92, 91]  # Last 10 days down

    # Volume: last 10 down-days have 800k, 700k, ..., 100k (max = 800k)
    # Last day: 1M volume (exceeds 800k)
    volume_values = [500000] * 50 + [
        800000,
        700000,
        600000,
        500000,
        400000,
        300000,
        200000,
        100000,
        100000,
        1000000,
    ]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": [c + 1 for c in close_values],
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    # Verify 50MA is close to current price (within 2%)
    # 50MA ≈ avg of last 50 closes = (100*50 + 99+98+...+90)/50 ≈ 95
    # Current close = 90, distance = (90-95)/95 ≈ -5.3% (NOT within 2%)
    # Adjust close to be within 2%
    df.loc[df.index[-1], "Close"] = df.loc[df.index[-1], "SMA_50"] * 1.01  # +1% from 50MA

    result = analyze_volume(df)

    assert any("Pocket Pivot" in sig for sig in result.signals), (
        f"Expected Pocket Pivot, got: {result.signals}"
    )
    assert result.score >= 25, f"Expected Pocket Pivot score 25, got: {result.score}"
    assert any("거래량" in str(e) for e in result.evidence)


def test_pocket_pivot_volume_not_exceeded():
    """Pocket Pivot Failed: Down-day volume does NOT exceed max of last 10 down-days."""
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    close_values = [100.0] * 50 + [99, 98, 97, 96, 95, 94, 93, 92, 91, 90]
    open_values = [100.5] * 50 + [100, 99, 98, 97, 96, 95, 94, 93, 92, 91]

    # Volume: last down-days have 1M, 900k, ..., 200k (max = 1M)
    # Last day: 800k (does NOT exceed 1M)
    volume_values = [500000] * 50 + [
        1000000,
        900000,
        800000,
        700000,
        600000,
        500000,
        400000,
        300000,
        200000,
        800000,
    ]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": [c + 1 for c in close_values],
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    # Adjust close to be within 2% of 50MA
    df.loc[df.index[-1], "Close"] = df.loc[df.index[-1], "SMA_50"] * 1.01

    result = analyze_volume(df)

    # Should NOT detect Pocket Pivot
    assert all("Pocket Pivot" not in sig for sig in result.signals), (
        f"Should not detect Pocket Pivot, got: {result.signals}"
    )


def test_pocket_pivot_not_near_50ma():
    """Pocket Pivot Failed: Price NOT near 50MA (±2%)."""
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    close_values = [100.0] * 50 + [
        99,
        98,
        97,
        96,
        95,
        94,
        93,
        92,
        91,
        80,
    ]  # Last close far from 50MA
    open_values = [100.5] * 50 + [100, 99, 98, 97, 96, 95, 94, 93, 92, 81]

    # Volume: last day exceeds all previous down-day volumes
    volume_values = [500000] * 50 + [
        800000,
        700000,
        600000,
        500000,
        400000,
        300000,
        200000,
        100000,
        100000,
        1000000,
    ]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": [c + 1 for c in close_values],
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    # Last close = 80, 50MA ≈ 95, distance ≈ -15.8% (NOT within 2%)
    result = analyze_volume(df)

    # Should NOT detect Pocket Pivot
    assert all("Pocket Pivot" not in sig for sig in result.signals), (
        f"Should not detect Pocket Pivot, got: {result.signals}"
    )


def test_tennis_ball_detected():
    """Tennis Ball: Down-day with low volume (<50% avg) suggests bounce."""
    # Create 30 days with avg volume 1M
    # Last 5 days: down days with normal volume
    # Last day: down day with 400k volume (40% of avg)

    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    close_values = [100.0] * 25 + [99, 98, 97, 96, 95]  # Last 5 days declining
    open_values = [100.5] * 25 + [100, 99, 98, 97, 96]  # Last 5 days down

    # Volume: avg = 1M, last day = 400k
    volume_values = [1000000] * 29 + [400000]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": [c + 1 for c in close_values],
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_volume(df)

    assert any("Tennis Ball" in sig or "반등" in sig for sig in result.signals), (
        f"Expected Tennis Ball, got: {result.signals}"
    )
    assert result.score >= 15, f"Expected Tennis Ball score 15, got: {result.score}"


def test_egg_detected():
    """Egg: Down-day with high volume (>150% avg) warns of further downside."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    close_values = [100.0] * 25 + [99, 98, 97, 96, 95]
    open_values = [100.5] * 25 + [100, 99, 98, 97, 96]

    # Volume: avg = 1M, last day = 1.6M (160% of avg)
    volume_values = [1000000] * 29 + [1600000]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": [c + 1 for c in close_values],
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_volume(df)

    assert any("Egg" in sig or "추가 하락" in sig for sig in result.signals), (
        f"Expected Egg, got: {result.signals}"
    )
    # Egg scores -15 points (first negative score!)
    assert result.score == -15, f"Expected Egg score -15, got: {result.score}"


def test_tennis_ball_egg_normal_volume():
    """Neither Tennis Ball nor Egg: Down-day with normal volume."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    close_values = [100.0] * 25 + [99, 98, 97, 96, 95]
    open_values = [100.5] * 25 + [100, 99, 98, 97, 96]

    # Volume: avg = 1M, last day = 1M (100% of avg, between 50%-150%)
    volume_values = [1000000] * 30

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": [c + 1 for c in close_values],
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_volume(df)

    # Should NOT detect Tennis Ball or Egg
    assert all("Tennis Ball" not in sig and "Egg" not in sig for sig in result.signals), (
        f"Should not detect Tennis Ball/Egg, got: {result.signals}"
    )


def test_power_gap_up_detected():
    """Power Gap Up: Gap ≥4% with 3x volume surge."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")

    # Normal days with close ≈ 100
    close_values = [100.0] * 28

    # Day 28 (prev): High = 100, Close = 100
    # Day 29 (last): Open = 105 (5% gap from prev high), Close = 106
    close_values.append(100)  # Day 28
    close_values.append(106)  # Day 29

    high_values = [c + 1 for c in close_values]
    high_values[-2] = 100  # Day 28 high = 100
    high_values[-1] = 107  # Day 29 high = 107

    open_values = [c - 0.5 for c in close_values]
    open_values[-1] = 105  # Day 29 open = 105 (gap from 100)

    # Volume: avg = 1M, last day = 3.5M (3.5x surge)
    volume_values = [1000000] * 29 + [3500000]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": high_values,
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_volume(df)

    assert any("Power Gap Up" in sig or "갭업" in sig for sig in result.signals), (
        f"Expected Power Gap Up, got: {result.signals}"
    )
    assert result.score >= 20, f"Expected Power Gap Up score 20, got: {result.score}"


def test_power_gap_up_insufficient_volume():
    """Power Gap Up Failed: Gap ≥4% but volume <3x."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    close_values = [100.0] * 28 + [100, 106]

    high_values = [c + 1 for c in close_values]
    high_values[-2] = 100
    high_values[-1] = 107

    open_values = [c - 0.5 for c in close_values]
    open_values[-1] = 105  # 5% gap

    # Volume: avg = 1M, last day = 2M (2x, NOT 3x)
    volume_values = [1000000] * 29 + [2000000]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": high_values,
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_volume(df)

    # Should NOT detect Power Gap Up (volume insufficient)
    assert all("Power Gap Up" not in sig for sig in result.signals), (
        f"Should not detect Power Gap Up, got: {result.signals}"
    )


def test_power_gap_up_insufficient_gap():
    """Power Gap Up Failed: Volume 3x but gap <4%."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    close_values = [100.0] * 28 + [100, 102]

    high_values = [c + 1 for c in close_values]
    high_values[-2] = 100
    high_values[-1] = 103

    open_values = [c - 0.5 for c in close_values]
    open_values[-1] = 101  # 1% gap (NOT 4%)

    # Volume: avg = 1M, last day = 3.5M (3.5x)
    volume_values = [1000000] * 29 + [3500000]

    df = pd.DataFrame(
        {
            "Open": open_values,
            "High": high_values,
            "Low": [c - 1 for c in close_values],
            "Close": close_values,
            "Volume": volume_values,
        },
        index=dates,
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    result = analyze_volume(df)

    # Should NOT detect Power Gap Up (gap insufficient)
    assert all("Power Gap Up" not in sig for sig in result.signals), (
        f"Should not detect Power Gap Up, got: {result.signals}"
    )
