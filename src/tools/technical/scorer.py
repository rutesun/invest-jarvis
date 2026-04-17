from datetime import UTC, datetime

import pandas as pd

from src.tools.technical.components.crsi import analyze_crsi
from src.tools.technical.components.divergence import analyze_divergence
from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.components.patterns import analyze_patterns
from src.tools.technical.components.risk import analyze_risk
from src.tools.technical.components.supertrend import analyze_supertrend
from src.tools.technical.components.velocity import analyze_velocity
from src.tools.technical.components.volume import analyze_volume
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.models import TechnicalResult


class TechnicalScorer:
    """Unified scoring system for technical analysis."""

    def __init__(self):
        self.calculator = IndicatorCalculator()

    def score(self, df: pd.DataFrame, ticker: str | None = None) -> TechnicalResult:
        """Calculate technical score from OHLCV data."""
        # Analyze with each component
        minervini_result = analyze_minervini(df)
        velocity_result = analyze_velocity(df)
        crsi_result = analyze_crsi(df)
        volume_result = analyze_volume(df)
        patterns_result = analyze_patterns(df)
        supertrend_result = analyze_supertrend(df)
        divergence_result = analyze_divergence(df)
        risk_result = analyze_risk(df)

        # Aggregate component results
        components = {
            "minervini": {
                "score": minervini_result.score,
                "signals": minervini_result.signals,
                "evidence": minervini_result.evidence,
                "metrics": minervini_result.metrics,
            },
            "velocity": {
                "score": velocity_result.score,
                "signals": velocity_result.signals,
                "evidence": velocity_result.evidence,
                "metrics": velocity_result.metrics,
            },
            "crsi": {
                "score": crsi_result.score,
                "signals": crsi_result.signals,
                "evidence": crsi_result.evidence,
                "metrics": crsi_result.metrics,
            },
            "volume": {
                "score": volume_result.score,
                "signals": volume_result.signals,
                "evidence": volume_result.evidence,
                "metrics": volume_result.metrics,
            },
            "patterns": {
                "score": patterns_result.score,
                "signals": patterns_result.signals,
                "evidence": patterns_result.evidence,
                "metrics": patterns_result.metrics,
            },
            "supertrend": {
                "score": supertrend_result.score,
                "signals": supertrend_result.signals,
                "evidence": supertrend_result.evidence,
                "metrics": supertrend_result.metrics,
            },
            "divergence": {
                "score": divergence_result.score,
                "signals": divergence_result.signals,
                "evidence": divergence_result.evidence,
                "metrics": divergence_result.metrics,
            },
            "risk": {
                "score": risk_result.score,
                "signals": risk_result.signals,
                "evidence": risk_result.evidence,
                "metrics": risk_result.metrics,
            },
        }

        # Calculate total score
        total_score = sum(comp["score"] for comp in components.values())

        # Create snapshot
        snapshot = self.calculator.create_snapshot(df)

        return TechnicalResult(
            ticker=ticker,
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components=components,
            total_score=total_score,
        )
