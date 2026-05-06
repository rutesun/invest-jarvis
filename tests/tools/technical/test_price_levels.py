# tests/tools/technical/test_price_levels.py

import pandas as pd
import pytest

from src.tools.technical.models import IndicatorSnapshot, PriceLevel, PriceLevels
from src.tools.technical.price_levels import (
    calculate_fibonacci_levels,
    deduplicate_levels,
    get_fibonacci_base_points,
    identify_key_levels,
    select_execution_levels,
)


def test_fibonacci_levels_calculation():
    """Test Fibonacci retracement and extension"""
    fib = calculate_fibonacci_levels(high=200.0, low=100.0)

    # Retracements
    assert fib["fib_0.382"] == pytest.approx(161.8, rel=0.01)
    assert fib["fib_0.618"] == pytest.approx(138.2, rel=0.01)

    # Extensions
    assert fib["fib_1.618"] == pytest.approx(261.8, rel=0.01)


def test_fibonacci_base_points_swing_priority():
    """Test swing points used if within 6 months"""
    df = pd.DataFrame(
        {"High": [100, 110, 105, 115, 100], "Low": [90, 95, 90, 95, 85]},
        index=pd.date_range(end=pd.Timestamp.now(), periods=5, freq="D"),
    )

    snapshot = IndicatorSnapshot(price=100.0, change_pct=0.0, swing_high=115.0, swing_low=85.0)

    high, low = get_fibonacci_base_points(df, snapshot)

    assert high == 115.0  # Swing high
    assert low == 85.0  # Swing low


def test_deduplicate_levels_basic():
    """Test deduplication with ±1% threshold"""
    levels = [
        PriceLevel(price=100.0, type="sma_50", distance_pct=-5.0, description="50일선"),
        PriceLevel(price=100.5, type="pivot_s1", distance_pct=-4.9, description="피봇"),
        PriceLevel(price=110.0, type="sma_20", distance_pct=+5.0, description="20일선"),
    ]

    unique = deduplicate_levels(levels, current_price=105.0, base_threshold=0.01)

    assert len(unique) == 2  # 100.0 and 100.5 merged
    assert unique[0].type == "sma_50"  # Higher priority


def test_identify_key_levels_integration():
    """Test full price level identification"""
    snapshot = IndicatorSnapshot(
        price=200.0,
        change_pct=0.0,
        sma_20=205.0,
        sma_50=175.0,
        sma_200=150.0,
        support_s1=187.0,
        resistance_r1=210.0,
        swing_high=215.0,
        swing_low=182.0,
        atr=8.0,
    )

    pattern_results = {}  # Empty for this test

    levels = identify_key_levels(
        snapshot=snapshot, pattern_results=pattern_results, lookback_high=220.0, lookback_low=140.0
    )

    assert levels.current_price == 200.0
    assert len(levels.support_levels) > 0
    assert len(levels.resistance_levels) > 0
    # Supports sorted by price descending (closest first)
    assert levels.support_levels[0].price > levels.support_levels[-1].price


def test_select_execution_levels_prefers_nearest_priority_levels():
    levels = PriceLevels(
        current_price=200.0,
        support_levels=[
            PriceLevel(price=198.0, type="pivot_s1", distance_pct=-1.0, description="피봇"),
            PriceLevel(price=195.0, type="atr_support_1x", distance_pct=-2.5, description="ATR"),
        ],
        resistance_levels=[
            PriceLevel(price=203.0, type="sma_20", distance_pct=1.5, description="20일선"),
            PriceLevel(price=205.0, type="fib_0.382", distance_pct=2.5, description="피보나치"),
        ],
    )

    selected = select_execution_levels(levels, max_count=3)

    assert [item.type for item in selected] == ["pivot_s1", "sma_20", "atr_support_1x"]
