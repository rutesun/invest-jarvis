import pandas as pd

from src.tools.technical.components.swing_extractor import SwingExtractor, extract_swing_candidates


def _build_test_df() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=7, freq="D")
    return pd.DataFrame(
        {
            "Open": [10, 10, 10, 10, 10, 10, 10],
            "High": [12, 13, 15, 14, 13, 16, 12],
            "Low": [8, 7, 6, 7, 8, 5, 7],
            "Close": [10, 11, 12, 11, 10, 12, 9],
            "Volume": [100, 110, 120, 130, 140, 150, 160],
        },
        index=dates,
    )


def test_extract_swing_candidates_returns_demand_swings():
    df = _build_test_df()

    swings = extract_swing_candidates(df, side="demand", window=3)

    assert len(swings) == 2
    assert swings[0].price == 6.0
    assert swings[1].price == 5.0
    assert [s.volume for s in swings] == [120.0, 150.0]


def test_extract_swing_candidates_returns_supply_swings():
    df = _build_test_df()

    swings = extract_swing_candidates(df, side="supply", window=3)

    assert len(swings) == 2
    assert swings[0].price == 15.0
    assert swings[1].price == 16.0
    assert [s.volume for s in swings] == [120.0, 150.0]


def test_swing_extractor_extracts_both_sides():
    df = _build_test_df()

    output = SwingExtractor(window=3).extract(df)

    assert len(output.demand_candidates) == 2
    assert len(output.supply_candidates) == 2
