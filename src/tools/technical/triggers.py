"""Legacy presentation adapter over the common trigger numerical owner."""

from datetime import date

import pandas as pd

from src.tools.technical.context import pattern_threshold_snapshot
from src.tools.technical.scorecard_models import (
    AnalysisTriggerEvent,
    Direction,
    Evidence,
    Importance,
)
from src.tools.technical.trigger_registry import TRIGGER_RULES


def detect_analysis_triggers(
    df: pd.DataFrame, *, as_of: date | None = None, display_bars: int = 20
) -> list[AnalysisTriggerEvent]:
    """Return recent events and their status as known at the requested session."""
    from src.tools.technical.chart_analysis import trigger_events

    rules = {rule.code: rule for rule in TRIGGER_RULES}
    return [
        AnalysisTriggerEvent(
            **vars(event),
            direction=Direction.RISING if rules[event.code].sense == "up" else Direction.FALLING,
            evidence=[
                Evidence(
                    code=event.code,
                    message=rules[event.code].occurrence_predicate,
                    observed_value=event.observed_value,
                    reference_value=event.reference_value,
                    importance=Importance.MEDIUM,
                    source=event.source,
                )
            ],
        )
        for event in trigger_events.detect_trigger_events(
            df,
            as_of=as_of,
            display_bars=display_bars,
            thresholds_by_rule={
                rule.code: pattern_threshold_snapshot(rule.code) for rule in TRIGGER_RULES
            },
        )
    ]
