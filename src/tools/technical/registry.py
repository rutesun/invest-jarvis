from src.tools.technical.base import BaseStrategy
from src.tools.technical.strategies.disparity import DisparityStrategy
from src.tools.technical.strategies.divergence import DivergenceStrategy
from src.tools.technical.strategies.oscillator import OscillatorStrategy
from src.tools.technical.strategies.risk import RiskStrategy
from src.tools.technical.strategies.trend import TrendStrategy


# Strategy mapping
STRATEGY_MAP = {
    "trend": TrendStrategy,
    "oscillator": OscillatorStrategy,
    "divergence": DivergenceStrategy,
    "disparity": DisparityStrategy,
    "risk": RiskStrategy,
}


class StrategyRegistry:
    """Registry for technical analysis strategies."""

    def __init__(self):
        self._strategies: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        """Register a strategy."""
        self._strategies[strategy.name] = strategy

    def unregister(self, name: str) -> None:
        """Unregister a strategy."""
        if name in self._strategies:
            del self._strategies[name]

    def get(self, name: str) -> BaseStrategy | None:
        """Get a strategy by name."""
        return self._strategies.get(name)

    def get_all(self) -> list[BaseStrategy]:
        """Get all registered strategies."""
        return list(self._strategies.values())

    @classmethod
    def from_config(cls, strategy_names: list[str]) -> "StrategyRegistry":
        """Create registry from config list."""
        registry = cls()
        for name in strategy_names:
            if name in STRATEGY_MAP:
                registry.register(STRATEGY_MAP[name]())
        return registry
