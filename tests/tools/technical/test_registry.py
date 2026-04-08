import pytest
from src.tools.technical.registry import StrategyRegistry
from src.tools.technical.strategies.trend import TrendStrategy


def test_registry_register():
    registry = StrategyRegistry()
    strategy = TrendStrategy()
    registry.register(strategy)

    assert "trend" in registry._strategies
    assert registry.get("trend") == strategy


def test_registry_get_all():
    registry = StrategyRegistry()
    registry.register(TrendStrategy())

    strategies = registry.get_all()
    assert len(strategies) == 1
    assert strategies[0].name == "trend"


def test_registry_unregister():
    registry = StrategyRegistry()
    registry.register(TrendStrategy())
    registry.unregister("trend")

    assert "trend" not in registry._strategies


def test_registry_from_config():
    registry = StrategyRegistry.from_config(["trend"])
    strategies = registry.get_all()

    assert len(strategies) == 1
    assert strategies[0].name == "trend"
