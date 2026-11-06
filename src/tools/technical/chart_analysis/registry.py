"""Finite detector catalog from common-chart-rule-map; consumers/policies stay outside."""

from dataclasses import dataclass
from typing import Any

from src.tools.technical.chart_analysis._legacy_structure import STATE_WINDOW_PARAMETERS
from src.tools.technical.chart_analysis.models import RuleRequest
from src.tools.technical.chart_analysis.trigger_catalog import TRIGGER_RULES


COMPAT_VERSION = "COMPAT_AD880AF_V1"
RS_ALIGNMENT = "PLAYBOOK_RS_ALIGNMENT_AD880AF"
SESSION_ALIGNMENT = "SESSION_V1"


@dataclass(frozen=True)
class RuleDefinition(RuleRequest):
    source_keys: tuple[str, ...] = ()


def _entry(
    rule_id: str,
    source: str,
    parameters: dict[str, Any] | None = None,
    *,
    version: str = COMPAT_VERSION,
    roles: tuple[str, ...] = ("instrument",),
    alignment: str = SESSION_ALIGNMENT,
) -> RuleDefinition:
    return RuleDefinition(rule_id, version, parameters or {}, roles, alignment, (source,))


_SIMPLE = (
    ("legacy.indicators", "F01"),
    ("legacy.extrema.order5", "F03"),
    ("chart.vcp.legacy", "T06"),
    ("chart.pocket_pivot.down_candle", "T07"),
    ("chart.power_gap", "T08"),
    ("chart.context.breakdown", "T09"),
    ("chart.stage2.minervini", "L01"),
    ("chart.velocity.legacy", "L02"),
    ("chart.crsi.legacy", "L02"),
    ("chart.supertrend.legacy", "L02"),
    ("chart.legacy.patterns_extra", "L03"),
    ("chart.legacy.volume_extra", "L03"),
    ("legacy.confluence", "L04"),
    ("legacy.divergence", "L04"),
    ("chart.close_breakout.nanmax", "L06"),
    ("chart.structure_breakdown.swing", "S02"),
    ("chart.deep_recovery.swing", "S02"),
    ("chart.vcp.playbook", "P01"),
    ("chart.accumulation.days", "P02"),
)


RULE_REGISTRY: tuple[RuleDefinition, ...] = (
    _entry("chart.features.strict", "Quality materials", version="CHART_FEATURE_V1"),
    _entry("chart.legacy.state_windows", "L05/L06/Scorecard", STATE_WINDOW_PARAMETERS),
    *(_entry(rule_id, source) for rule_id, source in _SIMPLE),
    *(
        _entry("feature.window", "F02", {"feature_key": key})
        for key in (
            "SMA_150_Slope_21",
            "SMA_20_Slope_5",
            "High_20_Prev",
            "High_50_Prev",
            "Low_20",
            "Low_20_Prev",
            "Vol_SMA_20",
            "Vol_SMA_20_Prev",
            "Vol_SMA_5",
            "Vol_SMA_20_Shift5",
            "High_52w",
            "Low_52w",
        )
    ),
    *(_entry("chart.pivot.span3", "F04", {"final_mask": mask}) for mask in (False, True)),
    *(
        _entry(trigger.code, "T01-T09", version=trigger.trigger_version)
        for trigger in TRIGGER_RULES
    ),
    *(_entry("chart.close_breakout.strict", "S01/appendix", {"lookback": n}) for n in (20, 50)),
    *(
        _entry("OBSERVATION_V1", "O01", {"code": code}, version="OBSERVATION_PARAMS_V1")
        for code in (
            "HIGHER_LOW",
            "HIGHER_HIGH",
            "LOWER_HIGH",
            "LOWER_LOW",
            "VOLUME_CONTRACTION",
            "UP_VOLUME_EXPANSION",
            "DOWN_VOLUME_EXPANSION",
        )
    ),
    _entry("chart.momentum.deceleration", "O02", version="OBSERVATION_PARAMS_V1"),
    *(
        _entry(
            "chart.momentum.reacceleration", "O02", {"mode": mode}, version="OBSERVATION_PARAMS_V1"
        )
        for mode in (
            "SMA20_TURN",
            "SMA20_TURN_POSITIVE_RETURN",
            "SMA20_TURN_HIGH_BREAK",
        )
    ),
    _entry(
        "chart.anchor.break_reclaim",
        "O03",
        {"break_buffer_atr": 0.0, "reclaim_buffer_atr": 0.0},
        version="OBSERVATION_PARAMS_V1",
    ),
    _entry("chart.market.regime", "P03", roles=("market",)),
    _entry("chart.rs", "P03", roles=("instrument", "market"), alignment=RS_ALIGNMENT),
    _entry(
        "chart.low_break_volume",
        "appendix",
        {"lookback": 20, "volume_ratio": 1.5},
        version="CHART_RULE_V1",
    ),
    _entry(
        "chart.down_volume_weak_close",
        "appendix",
        {"volume_ratio": 1.5, "close_location": 0.25},
        version="CHART_RULE_V1",
    ),
    _entry("chart.extension.sma20", "appendix", {"extension": 0.12}, version="CHART_RULE_V1"),
    _entry("chart.rsi.wilder", "appendix", {"threshold": 75}, version="CHART_RULE_V1"),
)


def rule_request(rule_id: str, parameters: dict[str, Any] | None = None) -> RuleRequest:
    """Return the declared default variant; callers may explicitly specialize parameters."""
    for entry in RULE_REGISTRY:
        if entry.rule_id == rule_id:
            return RuleRequest(
                entry.rule_id,
                entry.rule_version,
                entry.parameters if parameters is None else parameters,
                entry.input_roles,
                entry.alignment_version,
            )
    raise KeyError(f"Unknown chart rule: {rule_id}")
