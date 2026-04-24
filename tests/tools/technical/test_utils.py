# tests/tools/technical/test_utils.py

import pandas as pd
import pytest

from src.tools.technical.utils import (
    create_flat_price_series,
    create_noisy_series,
    create_random_walk,
    find_last_occurrence,
)


def test_find_last_occurrence_exact_match():
    """Test finding exact value"""
    df = pd.DataFrame({"High": [100, 105, 110, 105, 100]})

    idx = find_last_occurrence(df, "High", 110)
    assert idx == 2


def test_find_last_occurrence_with_tolerance():
    """Test tolerance for similar values (±0.1%)"""
    df = pd.DataFrame(
        {"High": [100.0, 105.0, 110.0, 110.05, 100.0]}  # 110.05 is within 0.1% of 110
    )

    idx = find_last_occurrence(df, "High", 110.0, tolerance=0.001)
    assert idx == 3  # Should match 110.05


def test_create_flat_price_series():
    """Test flat price series generator"""
    df = create_flat_price_series(days=120, price=100.0)

    assert len(df) == 120
    assert "Close" in df.columns
    assert df["Close"].mean() == pytest.approx(100.0, abs=0.5)
    assert df["Close"].std() < 0.5  # Very flat


def test_create_noisy_series():
    """Test noisy series generator"""
    df = create_noisy_series(days=120, base=100.0, noise=0.02)

    assert len(df) == 120
    assert "Close" in df.columns
    assert df["Close"].mean() == pytest.approx(100.0, abs=5.0)


def test_create_random_walk():
    """Test random walk generator"""
    df = create_random_walk(days=120, start=100.0)

    assert len(df) == 120
    assert "Close" in df.columns
    # Random walk will deviate from start, just check it's reasonable
    assert df["Close"].iloc[0] > 50.0
    assert df["Close"].iloc[0] < 150.0
