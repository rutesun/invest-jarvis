from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SwingCandidate:
    price: float
    timestamp: pd.Timestamp
    volume: float


@dataclass(frozen=True)
class SwingExtractorOutput:
    demand_candidates: list[SwingCandidate]
    supply_candidates: list[SwingCandidate]


def extract_swing_candidates(
    df: pd.DataFrame,
    *,
    side: str,
    window: int,
) -> list[SwingCandidate]:
    value_col = "Low" if side == "demand" else "High"
    rolling = (
        df[value_col].rolling(window=window, center=True, min_periods=window).min()
        if side == "demand"
        else df[value_col].rolling(window=window, center=True, min_periods=window).max()
    )
    swing_rows = df[df[value_col] == rolling]
    return [
        SwingCandidate(
            price=float(row[value_col]),
            timestamp=pd.Timestamp(index),
            volume=float(row.get("Volume", 0.0)),
        )
        for index, row in swing_rows.iterrows()
    ]


class SwingExtractor:
    def __init__(self, *, window: int):
        self.window = window

    def extract(self, df: pd.DataFrame) -> SwingExtractorOutput:
        return SwingExtractorOutput(
            demand_candidates=extract_swing_candidates(
                df,
                side="demand",
                window=self.window,
            ),
            supply_candidates=extract_swing_candidates(
                df,
                side="supply",
                window=self.window,
            ),
        )
