import pandas as pd

from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult


class MockStrategy(BaseStrategy):
    name = "mock"
    description = "Mock strategy for testing"

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        return StrategyResult(
            name=self.name,
            status="중립",
            confidence=50.0,
            signals=[],
            evidence=[],
            metrics={},
        )


def test_base_strategy_interface():
    strategy = MockStrategy()
    assert strategy.name == "mock"
    assert strategy.description == "Mock strategy for testing"

    df = pd.DataFrame({"Close": [100, 101, 102]})
    result = strategy.analyze(df)

    assert isinstance(result, StrategyResult)
    assert result.name == "mock"
