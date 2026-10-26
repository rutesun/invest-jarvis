"""Replay Analysis Trigger events from the observed exchange-session prefix."""

import math
from datetime import date

import pandas as pd

from src.tools.technical.components.patterns import _detect_vcp
from src.tools.technical.components.volume import _detect_pocket_pivot, _detect_power_gap_up
from src.tools.technical.context import build_market_context
from src.tools.technical.scorecard_models import (
    AnalysisTriggerEvent,
    Direction,
    Evidence,
    Importance,
    TriggerStatus,
)
from src.tools.technical.trigger_registry import TRIGGER_RULES, TriggerRuleDefinition


def _value(df: pd.DataFrame, position: int, column: str | None) -> float | None:
    if column == "ZERO":
        return 0.0
    if column is None or column not in df or position < 0:
        return None
    value = df.iloc[position][column]
    if pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _relation(left: float | None, right: float | None, sense: str) -> bool | None:
    if left is None or right is None:
        return None
    return left > right if sense == "up" else left < right


def _state(
    df: pd.DataFrame, position: int, rule: TriggerRuleDefinition
) -> tuple[bool | None, float | None, float | None]:
    if rule.kind in ("cross", "high_breakout"):
        if rule.kind == "high_breakout" and _value(df, position, "Close") is None:
            return None, None, None
        left = _value(df, position, rule.left)
        right = _value(df, position, rule.right)
        return _relation(left, right, rule.sense), left, right
    if rule.kind == "slope":
        assert rule.lookback_bars is not None
        current = _value(df, position, rule.left)
        past = _value(df, position - rule.lookback_bars, rule.left)
        difference = current - past if current is not None and past is not None else None
        return _relation(difference, 0.0, rule.sense), difference, 0.0

    if rule.kind == "supertrend":
        direction = _value(df, position, "SuperTrend_Dir")
        expected = 1.0 if rule.code.endswith("turn_up") else -1.0
        return (direction == expected if direction is not None else None), direction, expected

    prefix = df.iloc[: position + 1]
    if any(_value(df, position, column) is None for column in rule.required_inputs):
        return None, None, None
    close = _value(df, position, "Close")
    if rule.kind == "vcp":
        reference = _value(df, position, "High_20_Prev")
        detected = _detect_vcp(prefix)["score"] > 0
        return (
            bool(detected and close is not None and reference is not None and close > reference),
            close,
            reference,
        )
    if rule.kind == "pocket_pivot":
        result = _detect_pocket_pivot(prefix, prefix.iloc[-1])
        return bool(result["detected"]), close, _value(df, position, "SMA_50")
    if rule.kind == "power_gap":
        result = _detect_power_gap_up(prefix)
        return (
            bool(result["detected"]),
            _value(df, position, "Open"),
            _value(df, position - 1, "High"),
        )
    context = build_market_context(prefix)
    active = bool(
        context.is_breakdown
        and context.volume_ratio_20d is not None
        and context.volume_ratio_20d >= 1.3
    )
    return active, close, _value(df, position, "SMA_50")


def _occurred(
    df: pd.DataFrame, position: int, rule: TriggerRuleDefinition
) -> tuple[bool, float | None, float | None]:
    current, observed, reference = _state(df, position, rule)
    if current is not True:
        return False, observed, reference
    if rule.kind == "supertrend":
        expected_previous = -1.0 if rule.code.endswith("turn_up") else 1.0
        previous = _value(df, position - 1, "SuperTrend_Dir") == expected_previous
        return previous, observed, reference
    if rule.kind == "cross" and rule.source == "crsi":
        # analyze_crsi compares both sessions against the current band's value.
        prior_value = _value(df, position - 1, rule.left)
        if prior_value is None or reference is None:
            return False, observed, reference
        previous_breach = prior_value < reference if rule.sense == "up" else prior_value > reference
        return previous_breach, observed, reference
    else:
        previous, _, _ = _state(df, position - 1, rule)
    return previous is False, observed, reference


def _invalidated(
    df: pd.DataFrame, position: int, rule: TriggerRuleDefinition, event: AnalysisTriggerEvent
) -> bool:
    if rule.kind in ("cross", "slope", "supertrend"):
        state, _, _ = _state(df, position, rule)
        return state is False
    close = _value(df, position, "Close")
    if rule.kind == "vcp":
        return (
            close is not None
            and event.reference_value is not None
            and close <= event.reference_value
        )
    if rule.kind == "high_breakout":
        return (
            close is not None
            and event.reference_value is not None
            and close <= event.reference_value
        )
    if rule.kind == "pocket_pivot":
        return (
            close is not None and event.observed_value is not None and close < event.observed_value
        )
    if rule.kind == "power_gap":
        return (
            close is not None
            and event.reference_value is not None
            and close < event.reference_value
        )
    state, _, _ = _state(df, position, rule)
    return state is False


def detect_analysis_triggers(
    df: pd.DataFrame, *, as_of: date | None = None, display_bars: int = 20
) -> list[AnalysisTriggerEvent]:
    """Return recent events and their status as known at the requested session."""
    if df.empty or display_bars < 0 or not isinstance(df.index, pd.DatetimeIndex):
        return []
    if as_of is None:
        as_of = pd.Timestamp(df.index[-1]).date()
    observed = df.loc[df.index.date <= as_of].copy()
    if observed.empty:
        return []
    status_date = pd.Timestamp(observed.index[-1]).date()
    last = len(observed) - 1
    events: list[AnalysisTriggerEvent] = []
    for rule in TRIGGER_RULES:
        for position in range(max(2, last - display_bars), last + 1):
            occurred, value, reference = _occurred(observed, position, rule)
            if not occurred:
                continue
            event_date = pd.Timestamp(observed.index[position]).date()
            event = AnalysisTriggerEvent(
                code=rule.code,
                trigger_version=rule.trigger_version,
                occurred_on=event_date,
                bars_ago=last - position,
                direction=Direction.RISING if rule.sense == "up" else Direction.FALLING,
                source=rule.source,
                observed_value=value,
                reference_value=reference,
                status=TriggerStatus.ACTIVE,
                status_as_of=status_date,
                status_changed_on=event_date,
                status_reason="occurrence",
                expires_after_bars=rule.expires_after_bars,
                invalidated_on=None,
                expired_on=None,
                evidence=[
                    Evidence(
                        code=rule.code,
                        message=rule.occurrence_predicate,
                        observed_value=value,
                        reference_value=reference,
                        importance=Importance.MEDIUM,
                        source=rule.source,
                    )
                ],
            )
            for later in range(position + 1, last + 1):
                later_date = pd.Timestamp(observed.index[later]).date()
                if _invalidated(observed, later, rule, event):
                    event.status = TriggerStatus.INVALIDATED
                    event.invalidated_on = later_date
                    event.status_changed_on = later_date
                    event.status_reason = rule.invalidation_predicate
                    break
                if (
                    rule.expires_after_bars is not None
                    and later - position > rule.expires_after_bars
                ):
                    event.status = TriggerStatus.EXPIRED
                    event.expired_on = later_date
                    event.status_changed_on = later_date
                    event.status_reason = "validity TTL elapsed"
                    break
            events.append(event)
    return sorted(events, key=lambda event: (event.occurred_on, event.code), reverse=True)
