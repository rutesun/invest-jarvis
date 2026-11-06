"""Validated compatibility tuning inputs; numerical owners never read globals."""

from collections.abc import Mapping
from math import isfinite
from numbers import Integral, Real
from types import MappingProxyType


PATTERN_DEFAULTS = MappingProxyType(
    {
        "VCP_ATR_CONTRACTION": 0.20,
        "VCP_TIGHTNESS_MULTIPLIER": 0.5,
        "VCP_MIN_TIGHT_DAYS": 5,
        "VCP_RECENT_TIGHT_WINDOW": 3,
        "PP_SMA_DISTANCE_PCT": 0.02,
        "PP_LOOKBACK_DAYS": 10,
        "TENNIS_BALL_THRESHOLD": 0.5,
        "EGG_THRESHOLD": 1.5,
        "MEAN_REVERSION_LOOKBACK": 5,
        "GAP_SIZE_MIN_PCT": 0.04,
        "GAP_VOLUME_MULTIPLIER": 3.0,
        "VOLUME_SURGE_MULTIPLIER": 2.0,
        "VOLUME_MODERATE_MULTIPLIER": 1.2,
    }
)
_VCP = tuple(k for k in PATTERN_DEFAULTS if k.startswith("VCP_"))
_PP = ("PP_SMA_DISTANCE_PCT", "PP_LOOKBACK_DAYS")
_GAP = ("GAP_SIZE_MIN_PCT", "GAP_VOLUME_MULTIPLIER")
_VOLUME = (
    *_PP,
    *_GAP,
    "TENNIS_BALL_THRESHOLD",
    "EGG_THRESHOLD",
    "MEAN_REVERSION_LOOKBACK",
    "VOLUME_SURGE_MULTIPLIER",
    "VOLUME_MODERATE_MULTIPLIER",
)

FAMILY_THRESHOLDS = MappingProxyType(
    {
        "chart.vcp.legacy": _VCP,
        "chart.vcp.playbook": _VCP,
        "chart.pocket_pivot.down_candle": _PP,
        "chart.power_gap": _GAP,
        "chart.legacy.volume_extra": _VOLUME,
        "analysis.patterns.vcp_breakout": _VCP,
        "analysis.volume.pocket_pivot": _PP,
        "analysis.volume.power_gap_up": _GAP,
    }
)


def validated_thresholds(
    family: str, overrides: Mapping[str, int | float] | None = None
) -> dict[str, int | float]:
    """Signed finite ratios, positive windows and nonnegative tight counts.

    No arbitrary rule parameters or bool-as-int values are accepted. Missing
    overrides use the frozen AD880AF defaults, independently of runtime tuning.
    """
    keys = FAMILY_THRESHOLDS.get(family, ())
    if overrides is not None and not isinstance(overrides, Mapping):
        raise ValueError(f"{family} pattern thresholds must be a mapping")
    overrides = {} if overrides is None else dict(overrides)
    if set(overrides) - set(keys):
        raise ValueError(f"Unsupported {family} pattern thresholds")
    result = {key: overrides.get(key, PATTERN_DEFAULTS[key]) for key in keys}
    for key, value in result.items():
        if type(PATTERN_DEFAULTS[key]) is int:
            lower = 0 if key == "VCP_MIN_TIGHT_DAYS" else 1
            if isinstance(value, bool) or not isinstance(value, Integral) or value < lower:
                raise ValueError(f"{key} must be an integer >= {lower}")
            result[key] = int(value)
        elif isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
            raise ValueError(f"{key} must be a finite number")
        else:
            result[key] = float(value)
    return result


def canonical_threshold_overrides(
    family: str, values: Mapping[str, int | float]
) -> dict[str, int | float]:
    checked = validated_thresholds(family, values)
    return {key: value for key, value in checked.items() if value != PATTERN_DEFAULTS[key]}
