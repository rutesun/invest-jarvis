"""Convert chart-only strategy intent into a position directive."""

from collections.abc import Sequence

from src.position.models import DirectiveKind, PositionDirective
from src.strategies.models import (
    EntryIntent,
    EntryOpportunityStatus,
    ExitIntent,
    SignalEntryOpportunity,
    StrategySignal,
)
from src.strategies.signal_selection import select_latest_entry_signal


_EXIT_PRIORITY = (
    "SMA150_EXIT",
    "OVERHEAT_CORRECTION",
)


def decide_directive(entry: EntryIntent, exit: ExitIntent) -> PositionDirective:
    if exit is ExitIntent.NOT_EVALUATED:
        return PositionDirective(DirectiveKind.FREEZE)
    if exit is ExitIntent.EXIT:
        return PositionDirective(DirectiveKind.FLAT)
    if exit is ExitIntent.REDUCE:
        return PositionDirective(DirectiveKind.REDUCE_CURRENT_BY_FRACTION, 0.5)
    if entry is EntryIntent.ALLOW:
        return PositionDirective(DirectiveKind.BUILD_ONLY_TO_RISK_TARGET)
    return PositionDirective(DirectiveKind.KEEP_CURRENT)


def select_current_signal(signals: Sequence[StrategySignal]) -> StrategySignal | None:
    """Prefer safety Signals, then the latest representative Entry."""
    safety = next(
        (signal for code in _EXIT_PRIORITY for signal in signals if signal.code == code),
        None,
    )
    return safety if safety is not None else select_latest_entry_signal(signals)


def decide_signal_directive(
    current_signals: Sequence[StrategySignal], opportunity: SignalEntryOpportunity
) -> PositionDirective:
    selected = select_current_signal(current_signals)
    if selected is not None:
        if selected.code == "SMA150_EXIT":
            return PositionDirective(DirectiveKind.FLAT)
        if selected.code == "OVERHEAT_CORRECTION":
            return PositionDirective(DirectiveKind.REDUCE_CURRENT_BY_FRACTION, 0.5)
        if (
            opportunity.status is EntryOpportunityStatus.ALLOW
            and opportunity.evaluation_as_of == selected.occurred_on
            and opportunity.entry_signal is not None
            and opportunity.entry_signal.signal_id == selected.signal_id
        ):
            return PositionDirective(DirectiveKind.BUILD_ONLY_TO_RISK_TARGET)
    return PositionDirective(DirectiveKind.KEEP_CURRENT)
