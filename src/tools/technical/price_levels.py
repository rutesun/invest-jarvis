# src/tools/technical/price_levels.py

import pandas as pd

from src.tools.technical.models import (
    ChartPatternResult,
    IndicatorSnapshot,
    PriceLevel,
    PriceLevels,
)
from src.tools.technical.utils import find_last_occurrence


def calculate_fibonacci_levels(high: float, low: float) -> dict[str, float]:
    """피보나치 되돌림 및 확장 레벨"""
    diff = high - low
    return {
        # Retracements
        "fib_0.236": high - diff * 0.236,
        "fib_0.382": high - diff * 0.382,
        "fib_0.500": high - diff * 0.500,
        "fib_0.618": high - diff * 0.618,
        "fib_0.786": high - diff * 0.786,
        "fib_1.000": low,
        # Extensions
        "fib_1.272": high + diff * 0.272,
        "fib_1.618": high + diff * 0.618,
        "fib_2.000": high + diff * 1.000,
    }


def get_fibonacci_base_points(df: pd.DataFrame, snapshot: IndicatorSnapshot) -> tuple[float, float]:
    """피보나치 계산 기준 고점/저점 선택"""
    # Try swing points
    if snapshot.swing_high and snapshot.swing_low:
        swing_high_idx = find_last_occurrence(df, "High", snapshot.swing_high, tolerance=0.001)
        if swing_high_idx is not None:
            days_since_swing = len(df) - swing_high_idx - 1
            if days_since_swing <= 126:  # 6 months ≈ 126 trading days
                return snapshot.swing_high, snapshot.swing_low
    # Fallback: 6-month high/low
    high_6m = df["High"].tail(126).max()
    low_6m = df["Low"].tail(126).min()
    return high_6m, low_6m


def deduplicate_levels(
    levels: list[PriceLevel], current_price: float, base_threshold: float = 0.01
) -> list[PriceLevel]:
    """중복 레벨 제거 (현재가 대비 dynamic threshold)"""
    if not levels:
        return []
    levels_sorted = sorted(levels, key=lambda x: x.price)
    unique = [levels_sorted[0]]
    for level in levels_sorted[1:]:
        last_price = unique[-1].price
        distance_from_current = abs(level.price - current_price) / current_price
        threshold = base_threshold * (0.5 if distance_from_current < 0.05 else 1.0)
        if abs(level.price - last_price) / last_price > threshold:
            unique.append(level)
        else:
            priority_map = {"sma_": 3, "swing_": 3, "pivot_": 2, "fib_": 1, "atr_": 0}
            current_priority = max(
                (priority_map.get(k, 0) for k in priority_map if level.type.startswith(k)),
                default=0,
            )
            last_priority = max(
                (priority_map.get(k, 0) for k in priority_map if unique[-1].type.startswith(k)),
                default=0,
            )
            if current_priority > last_priority:
                unique[-1] = level
    return unique


def calculate_atr_levels(current_price: float, atr: float) -> dict[str, float]:
    """ATR 기반 지지/저항"""
    return {
        "atr_support_1x": current_price - atr,
        "atr_support_2x": current_price - 2 * atr,
        "atr_resistance_1x": current_price + atr,
        "atr_resistance_2x": current_price + 2 * atr,
    }


def identify_key_levels(
    snapshot: IndicatorSnapshot,
    pattern_results: dict[str, ChartPatternResult],
    lookback_high: float,
    lookback_low: float,
) -> PriceLevels:
    """모든 레벨 수집 → 중복 제거 → 가까운 순 정렬"""
    all_levels: list[PriceLevel] = []

    # 1. Moving averages
    for ma in [20, 50, 150, 200]:
        ma_val = getattr(snapshot, f"sma_{ma}", None)
        if ma_val:
            all_levels.append(
                PriceLevel(
                    price=ma_val,
                    type=f"sma_{ma}",
                    distance_pct=(ma_val - snapshot.price) / snapshot.price * 100,
                    description=f"{ma}일 이평선",
                )
            )

    # 2. Pivot points
    if snapshot.support_s1:
        all_levels.append(
            PriceLevel(
                price=snapshot.support_s1,
                type="pivot_s1",
                distance_pct=(snapshot.support_s1 - snapshot.price) / snapshot.price * 100,
                description="피봇 지지1",
            )
        )
    if snapshot.resistance_r1:
        all_levels.append(
            PriceLevel(
                price=snapshot.resistance_r1,
                type="pivot_r1",
                distance_pct=(snapshot.resistance_r1 - snapshot.price) / snapshot.price * 100,
                description="피봇 저항1",
            )
        )

    # 3. Swing points
    if snapshot.swing_high:
        all_levels.append(
            PriceLevel(
                price=snapshot.swing_high,
                type="swing_high",
                distance_pct=(snapshot.swing_high - snapshot.price) / snapshot.price * 100,
                description="스윙 고점",
            )
        )
    if snapshot.swing_low:
        all_levels.append(
            PriceLevel(
                price=snapshot.swing_low,
                type="swing_low",
                distance_pct=(snapshot.swing_low - snapshot.price) / snapshot.price * 100,
                description="스윙 저점",
            )
        )

    # 4. Fibonacci levels
    fib_levels = calculate_fibonacci_levels(lookback_high, lookback_low)
    for fib_name, fib_price in fib_levels.items():
        all_levels.append(
            PriceLevel(
                price=fib_price,
                type=fib_name,
                distance_pct=(fib_price - snapshot.price) / snapshot.price * 100,
                description=f"피보나치 {fib_name.replace('fib_', '')}",
            )
        )

    # 5. ATR levels (if available)
    if snapshot.atr:
        atr_levels = calculate_atr_levels(snapshot.price, snapshot.atr)
        for atr_name, atr_price in atr_levels.items():
            all_levels.append(
                PriceLevel(
                    price=atr_price,
                    type=atr_name,
                    distance_pct=(atr_price - snapshot.price) / snapshot.price * 100,
                    description=f"ATR {atr_name.replace('atr_', '').replace('_', ' ')}",
                )
            )

    # 6. Pattern breakout levels
    for pattern_name, result in pattern_results.items():
        if result.detected and result.breakout_level:
            all_levels.append(
                PriceLevel(
                    price=result.breakout_level,
                    type=f"pattern_{pattern_name}_breakout",
                    distance_pct=(result.breakout_level - snapshot.price) / snapshot.price * 100,
                    description=f"{result.pattern_name} 돌파",
                )
            )

    # Deduplicate
    unique_levels = deduplicate_levels(all_levels, snapshot.price, base_threshold=0.01)

    # Split into supports/resistances
    supports = [lv for lv in unique_levels if lv.price < snapshot.price]
    resistances = [lv for lv in unique_levels if lv.price > snapshot.price]

    # Sort: supports high to low, resistances low to high
    supports.sort(key=lambda x: x.price, reverse=True)
    resistances.sort(key=lambda x: x.price)

    # Extract targets from patterns
    targets = {}
    for pattern_name, result in pattern_results.items():
        if result.detected and "target" in result.key_levels:
            targets[f"{pattern_name}_target"] = result.key_levels["target"]

    # Add Fibonacci extension as target
    if "fib_1.618" in fib_levels:
        targets["fibonacci_extension_1.618"] = fib_levels["fib_1.618"]

    return PriceLevels(
        current_price=snapshot.price,
        support_levels=supports[:5],
        resistance_levels=resistances[:5],
        targets=targets,
    )


def select_execution_levels(levels: PriceLevels, max_count: int = 3) -> list[PriceLevel]:
    """실행용 핵심 line을 현재가 근접도와 타입 우선순위로 선택"""
    priority_order = {
        "pivot": 0,
        "sma": 1,
        "atr": 2,
        "fib": 3,
        "pattern": 4,
        "swing": 5,
    }
    all_levels = [*levels.support_levels, *levels.resistance_levels]
    return sorted(
        all_levels,
        key=lambda level: (
            abs(level.distance_pct),
            priority_order.get(level.type.split("_")[0], 9),
        ),
    )[:max_count]
