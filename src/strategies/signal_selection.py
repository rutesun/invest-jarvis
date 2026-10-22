"""Select a representative Entry without changing its downstream validity checks."""

from collections.abc import Sequence
from datetime import date

from src.strategies.models import StrategySignal


_ENTRY_PRIORITY = {
    "POST_OVERHEAT_RECOVERY_ENTRY": 0,
    "PULLBACK_REVERSAL_ENTRY": 1,
    "TREND_BREAKOUT_ENTRY": 2,
    "DEEP_RECOVERY_ENTRY": 3,
}


def select_latest_entry_signal(
    signals: Sequence[StrategySignal], *, as_of: date | None = None
) -> StrategySignal | None:
    """Prefer the latest Entry date, then the same-day representative type."""
    return max(
        (
            signal
            for signal in signals
            if signal.code in _ENTRY_PRIORITY and (as_of is None or signal.occurred_on <= as_of)
        ),
        key=lambda signal: (signal.occurred_on, -_ENTRY_PRIORITY[signal.code]),
        default=None,
    )
