import pytest
import pandas as pd
import numpy as np
from src.tools.screener.scoring import (
    score_accumulation,
    score_up_days,
    score_volume_burst,
    score_source_diversity,
    score_momentum,
)


def test_score_accumulation():
    trends = [
        {"total_net": 100},
        {"total_net": -50},
        {"total_net": 200},
        {"total_net": 300},
        {"total_net": -10},
        {"total_net": 150},
        {"total_net": 50},
        {"total_net": -20},
        {"total_net": 100},
        {"total_net": 80},
    ]
    score = score_accumulation(trends)
    # 7 positive days, net_sum > 0, score = 7 * 1.5 = 10.5
    assert score == 10.5


def test_score_accumulation_negative_sum():
    trends = [
        {"total_net": -100},
        {"total_net": -200},
        {"total_net": 10},
    ]
    score = score_accumulation(trends)
    assert score == 0.0  # net_sum < 0


def test_score_up_days():
    df = pd.DataFrame({
        "Open": [100, 101, 102, 100, 99],
        "Close": [101, 100, 103, 101, 98],  # up, down, up, up, down
    })
    days = score_up_days(df, window=5)
    assert days == 3


def test_score_volume_burst():
    score = score_volume_burst(vol_ratio=3.0)
    # clamp(3.0 - 1.5, 0, 8.0) = 1.5
    assert score == 1.5

    score = score_volume_burst(vol_ratio=10.0)
    # clamp(10.0 - 1.5, 0, 8.0) = 8.0
    assert score == 8.0

    score = score_volume_burst(vol_ratio=1.0)
    assert score == 0.0


def test_score_source_diversity():
    sources = ["theme", "volume_rank", "kis_rank"]
    bonus = score_source_diversity(sources)
    # weights: 1.0 + 1.5 + 1.5 = 4.0, raw = 3.0, bonus = min(10, 2.0 * 3.0) = 6.0
    assert bonus == 6.0


def test_score_source_diversity_single():
    sources = ["rise_rank"]
    bonus = score_source_diversity(sources)
    # weight: 1.0, raw = 0.0, bonus = 0.0
    assert bonus == 0.0


def test_score_momentum_breakout():
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    # consolidation then breakout
    close = np.concatenate([np.random.uniform(98, 102, 55), [103, 105, 107, 110, 112]])
    high = close + 1
    low = close - 1
    df = pd.DataFrame({
        "Open": close - 0.5,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": [1000000] * 60,
    }, index=dates)
    result = score_momentum(df)
    assert "breakout" in result
    assert "momentum_total" in result
