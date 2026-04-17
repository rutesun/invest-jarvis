from abc import ABC, abstractmethod

import pandas as pd

from src.tools.technical.models import StrategyResult


class BaseStrategy(ABC):
    """Abstract base class for technical analysis strategies."""

    name: str
    description: str

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        """Analyze price data and return strategy result."""
        pass

    def _safe_get(self, series: pd.Series, key: str, default: float = 0.0) -> float:
        """Safely get value from series."""
        val = series.get(key)
        if pd.isna(val) or val is None:
            return default
        return float(val)
