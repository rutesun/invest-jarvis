from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.tools.technical.components.chart_patterns import detect_chart_patterns
from src.tools.technical.components.swing_extractor import SwingExtractor, SwingExtractorOutput
from src.tools.technical.models import ChartPatternResult, IndicatorSnapshot


@dataclass(frozen=True)
class PatternEngineInput:
    df: pd.DataFrame
    snapshot: IndicatorSnapshot | None
    swings: SwingExtractorOutput


class PatternEngine:
    def __init__(self, *, swing_window: int = 5):
        self.swing_extractor = SwingExtractor(window=swing_window)

    def build_input(
        self,
        df: pd.DataFrame,
        snapshot: IndicatorSnapshot | None = None,
    ) -> PatternEngineInput:
        return PatternEngineInput(
            df=df,
            snapshot=snapshot,
            swings=self.swing_extractor.extract(df),
        )

    def detect(
        self,
        df: pd.DataFrame,
        snapshot: IndicatorSnapshot | None = None,
    ) -> dict[str, ChartPatternResult]:
        engine_input = self.build_input(df, snapshot)
        return detect_chart_patterns(
            engine_input.df,
            engine_input.snapshot,
            swings=engine_input.swings,
        )
