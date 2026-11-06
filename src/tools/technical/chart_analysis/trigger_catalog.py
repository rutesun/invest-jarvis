"""Versioned definitions for observable, strategy-independent chart events."""

from pydantic import BaseModel, ConfigDict


class TriggerRuleDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    trigger_version: str
    required_inputs: list[str]
    occurrence_predicate: str
    equality_policy: str
    invalidation_predicate: str
    expires_after_bars: int | None
    event_date_rule: str
    source: str
    missing_policy: str
    kind: str
    left: str | None = None
    right: str | None = None
    sense: str = "up"
    lookback_bars: int | None = None


_VERSION = "ANALYSIS_TRIGGER_V1"
_DATE = "current exchange session date on first false-to-true transition"
_MISSING = "skip occurrence or state transition when any required value is missing/non-finite"


def _cross(source: str, event: str, left: str, right: str, sense: str) -> TriggerRuleDefinition:
    relation = ">" if sense == "up" else "<"
    opposite = "<=" if sense == "up" else ">="
    return TriggerRuleDefinition(
        code=f"analysis.{source}.{event}",
        trigger_version=_VERSION,
        required_inputs=(left, right),
        occurrence_predicate=(
            f"previous {left} {'<' if sense == 'up' else '>'} current {right}; current {left} {relation} current {right}"
            if source == "crsi"
            else f"previous {left} {opposite} previous {right}; current {left} {relation} current {right}"
        ),
        equality_policy=(
            "equality on either side does not trigger the component's strict band hook"
            if source == "crsi"
            else f"equality belongs to previous/opposite side ({opposite}); strict {relation} triggers"
        ),
        invalidation_predicate=f"{left} {opposite} {right} on a later session",
        expires_after_bars=None,
        event_date_rule=_DATE,
        source=source,
        missing_policy=_MISSING,
        kind="cross",
        left=left,
        right=right,
        sense=sense,
    )


def _slope(length: int, sense: str) -> TriggerRuleDefinition:
    column = f"SMA_{length}"
    relation = ">" if sense == "up" else "<"
    opposite = "<=" if sense == "up" else ">="
    return TriggerRuleDefinition(
        code=f"analysis.sma.{length}.turn_{sense}",
        trigger_version=_VERSION,
        required_inputs=(column,),
        occurrence_predicate=(
            f"previous 21-session slope ({column}[t-1] - {column}[t-22]) {opposite} 0; "
            f"current 21-session slope ({column}[t] - {column}[t-21]) {relation} 0"
        ),
        equality_policy="zero slope is flat and can precede either turn",
        invalidation_predicate=f"{column} 21-session slope {opposite} 0 on a later session",
        expires_after_bars=None,
        event_date_rule=_DATE,
        source="sma",
        missing_policy="skip when current, previous, t-21, or t-22 SMA is missing/non-finite",
        kind="slope",
        left=column,
        sense=sense,
        lookback_bars=21,
    )


def _special(
    source: str,
    event: str,
    kind: str,
    inputs: tuple[str, ...],
    occurrence: str,
    invalidation: str,
    ttl: int | None,
    sense: str = "up",
) -> TriggerRuleDefinition:
    return TriggerRuleDefinition(
        code=f"analysis.{source}.{event}",
        trigger_version=_VERSION,
        required_inputs=inputs,
        occurrence_predicate=occurrence,
        equality_policy="threshold equality follows the referenced component; false-to-true only",
        invalidation_predicate=invalidation,
        expires_after_bars=ttl,
        event_date_rule=_DATE,
        source=source,
        missing_policy=_MISSING,
        kind=kind,
        sense=sense,
    )


def _high_breakout(length: int) -> TriggerRuleDefinition:
    reference = f"High_{length}_Prev"
    return TriggerRuleDefinition(
        code=f"analysis.price.high_{length}_breakout",
        trigger_version=_VERSION,
        required_inputs=("High", "Close", reference),
        occurrence_predicate=f"previous High <= previous {reference}; current High > current {reference}",
        equality_policy="equal high is not a breakout",
        invalidation_predicate="Close <= breakout day's previous-window high",
        expires_after_bars=None,
        event_date_rule=_DATE,
        source="price",
        missing_policy=_MISSING,
        kind="high_breakout",
        left="High",
        right=reference,
        sense="up",
    )


TRIGGER_RULES: tuple[TriggerRuleDefinition, ...] = (
    _cross("crsi", "upper_band_exit", "cRSI", "cRSI_HighBand", "down"),
    _cross("crsi", "lower_band_reentry", "cRSI", "cRSI_LowBand", "up"),
    *(
        _cross(source, event, left, right, sense)
        for source, left, right in (
            ("macd", "MACD", "MACD_Signal"),
            ("fast_macd", "MACD_Fast", "MACD_Fast_Signal"),
        )
        for event, sense in (("golden_cross", "up"), ("dead_cross", "down"))
    ),
    *(
        _cross(source, event, column, "ZERO", sense)
        for source, column in (("macd_hist", "MACD_Hist"), ("fast_macd_hist", "MACD_Fast_Hist"))
        for event, sense in (("positive_cross", "up"), ("negative_cross", "down"))
    ),
    *(_slope(length, sense) for length in (20, 50, 150, 200) for sense in ("up", "down")),
    *(
        _cross("price", f"sma{length}_{event}", "Close", f"SMA_{length}", sense)
        for length in (20, 50, 150, 200)
        for event, sense in (("cross_above", "up"), ("cross_below", "down"))
    ),
    *(
        _cross("sma", f"{short}_{long}.{event}", f"SMA_{short}", f"SMA_{long}", sense)
        for short, long in ((20, 50), (50, 150), (50, 200), (150, 200))
        for event, sense in (("golden_cross", "up"), ("dead_cross", "down"))
    ),
    *(
        _special(
            "supertrend",
            event,
            "supertrend",
            ("SuperTrend_Dir",),
            f"previous SuperTrend_Dir == {previous}; current SuperTrend_Dir == {current}",
            f"SuperTrend_Dir != {current} on a later session",
            None,
            "up" if current == 1 else "down",
        )
        for event, previous, current in (("turn_up", -1, 1), ("turn_down", 1, -1))
    ),
    *(_high_breakout(length) for length in (20, 50)),
    _special(
        "patterns",
        "vcp_breakout",
        "vcp",
        ("High", "Low", "ATR", "Close", "High_20_Prev"),
        "VCP component: >=20 bars, >=8 ATR; first-4 to last-4 ATR contraction >20%; Close > prior 20-day High",
        "Close <= event breakout reference",
        5,
    ),
    _special(
        "volume",
        "pocket_pivot",
        "pocket_pivot",
        ("Open", "Close", "Volume", "SMA_50"),
        "Close < Open, within 2% of SMA50, >=3 down days in prior 10, Volume > their maximum",
        "Close < event Close",
        10,
    ),
    _special(
        "volume",
        "power_gap_up",
        "power_gap",
        ("Open", "High", "Volume", "Vol_SMA_20"),
        "Open >= previous High * 1.04 and Volume >= current Vol_SMA_20 * 3",
        "Close < previous High gap floor",
        5,
    ),
    _special(
        "volume",
        "breakdown",
        "volume_breakdown",
        ("Close", "SMA_20", "SMA_50", "Volume", "Vol_SMA_20"),
        "market context is_breakdown (below SMA50 with volume >=1.3x, Supertrend sell flip, or below SMA20/SMA50 with negative 10-bar return) and volume ratio >=1.3",
        "breakdown condition no longer holds",
        5,
        "down",
    ),
)
