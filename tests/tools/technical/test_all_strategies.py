import numpy as np
import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.registry import StrategyRegistry


@pytest.fixture
def sample_df():
    """Create sample data for strategy testing."""
    dates = pd.date_range("2023-01-01", periods=300, freq="D")
    close = 100 + np.cumsum(np.random.randn(300) * 1.5)
    df = pd.DataFrame(
        {
            "Open": close - np.random.rand(300),
            "High": close + np.random.rand(300) * 2,
            "Low": close - np.random.rand(300) * 2,
            "Close": close,
            "Volume": np.random.randint(1000000, 5000000, 300),
        },
        index=dates,
    )
    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_all_strategies_from_config(sample_df):
    """Test that all 5 strategies can be loaded from config."""
    strategy_names = ["trend", "oscillator", "divergence", "disparity", "risk"]
    registry = StrategyRegistry.from_config(strategy_names)

    all_strategies = registry.get_all()
    assert len(all_strategies) == 5

    strategy_names_registered = {s.name for s in all_strategies}
    assert strategy_names_registered == {"trend", "oscillator", "divergence", "disparity", "risk"}


def test_all_strategies_execute(sample_df):
    """Test that all strategies can execute successfully."""
    strategy_names = ["trend", "oscillator", "divergence", "disparity", "risk"]
    registry = StrategyRegistry.from_config(strategy_names)

    for strategy in registry.get_all():
        result = strategy.analyze(sample_df)
        assert result.name in strategy_names
        assert result.status is not None
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 100
        assert isinstance(result.signals, list)
        assert isinstance(result.evidence, list)
        assert isinstance(result.metrics, dict)
