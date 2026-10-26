"""Chart-only strategy boundary."""

from typing import Protocol

from src.strategies.models import ChartBundle, StrategySignalBundle, StrategyVerdict
from src.strategies.swing_w150.parameters import SwingW150Parameters


class StrategyProtocol(Protocol):
    strategy_id: str
    strategy_version: str

    def evaluate(self, bundle: ChartBundle) -> StrategyVerdict: ...


class SignalStrategyProtocol(Protocol):
    strategy_id: str
    strategy_version: str
    parameters: SwingW150Parameters

    def evaluate_signals(self, bundle: ChartBundle) -> StrategySignalBundle: ...
