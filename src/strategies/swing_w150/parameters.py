"""Versioned SWING_W150 parameters and canonical identity."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Literal

from src.storage.canonical import canonical_bytes


@dataclass(frozen=True)
class SwingW150Parameters:
    parameter_set_version: str = "SWING_W150_V2_PARAMS_V1"
    minimum_history_bars: int = 250
    direction_lookback_bars: int = 21

    trend_breakout_lookback: int = 50
    trend_breakout_volume_multiple: float = 1.4
    deep_recovery_breakout_lookback: int = 20
    structure_breakdown_volume_multiple: float = 1.5
    structure_weak_close_location: float = 0.25

    overheat_extension: float = 0.40
    overheat_reset_extension: float = 0.20
    overheat_expiry_bars: int = 20
    post_correction_recovery_expiry_bars: int = 20

    pullback_support_sma_periods: tuple[int, ...] = (50, 150, 200)
    pullback_support_atr_distance: float = 0.5
    pullback_watch_expiry_bars: int = 10
    pullback_reversal_high_lookback: int = 1

    sma_exit_consecutive_closes: int = 2
    entry_opportunity_max_age_bars: int = 20
    entry_opportunity_max_extension: float = 0.05

    @property
    def parameter_fingerprint(self) -> str:
        return parameter_fingerprint(self)


@dataclass(frozen=True)
class SupportCycleParameters:
    normal_failure_closes: int | None = None
    immediate_failure_volume_ratio: float | None = None
    immediate_failure_close_location: float | None = None
    support_break_buffer_atr: float | None = None
    restart_mode: Literal["A", "B", "C", "D"] | None = None

    def __post_init__(self) -> None:
        count = self.normal_failure_closes
        if count is not None and (type(count) is not int or count <= 0):
            raise ValueError("normal_failure_closes must be a positive integer or None")
        ratio = self.immediate_failure_volume_ratio
        location = self.immediate_failure_close_location
        if (ratio is None) != (location is None):
            raise ValueError("immediate failure ratio and close location must be selected together")
        if ratio is not None and (not isfinite(ratio) or ratio <= 0):
            raise ValueError("immediate_failure_volume_ratio must be positive or None")
        if location is not None and (not isfinite(location) or not 0 <= location <= 1):
            raise ValueError("immediate_failure_close_location must be in [0, 1] or None")
        buffer = self.support_break_buffer_atr
        if buffer is not None and (not isfinite(buffer) or buffer < 0):
            raise ValueError("support_break_buffer_atr must be nonnegative or None")
        if self.restart_mode not in (None, "A", "B", "C", "D"):
            raise ValueError("unknown restart_mode")


@dataclass(frozen=True)
class SwingW150ParametersV2(SwingW150Parameters):
    """명시 선택용 schema. 선언만으로 새 support 정책을 활성화하지 않는다."""

    parameter_set_version: str = "SWING_W150_V2_PARAMS_V2"
    support_cycle: SupportCycleParameters = field(default_factory=SupportCycleParameters)
    pullback_policy_version: str = "SUPPORT_LADDER_V1"


V2_INACTIVE_REASON = (
    "SUPPORT_LADDER_V1 inactive: failure/immediate/restart UNRESOLVED; "
    "V1 default retained. Explicit immediate OFF is unsupported by the current schema."
)


def validate_pullback_policy(parameters: SwingW150Parameters) -> bool:
    """Only a fully selected explicit V2 payload may run the new policy."""
    if not isinstance(parameters, SwingW150ParametersV2):
        return False
    if parameters.pullback_policy_version != "SUPPORT_LADDER_V1":
        raise ValueError("unsupported pullback_policy_version")
    missing = [name for name, value in asdict(parameters.support_cycle).items() if value is None]
    if missing:
        raise ValueError(
            "SUPPORT_LADDER_V1 inactive: UNRESOLVED "
            + ", ".join(missing)
            + "; explicit immediate OFF is unsupported by the current schema"
        )
    return True


def parameter_fingerprint(parameters: SwingW150Parameters) -> str:
    """Hash the canonical JSON representation of all parameter fields."""
    return hashlib.sha256(canonical_bytes(asdict(parameters))).hexdigest()


class ParameterRegistry:
    """Keep each production parameter version bound to one payload."""

    def __init__(self, parameters: tuple[SwingW150Parameters, ...]):
        self._parameters_by_version = {
            parameter.parameter_set_version: parameter for parameter in parameters
        }
        if len(self._parameters_by_version) != len(parameters):
            raise ValueError("parameter versions must be unique")

    def get(self, parameter_set_version: str) -> SwingW150Parameters:
        return self._parameters_by_version[parameter_set_version]

    def validate(self, parameters: SwingW150Parameters) -> SwingW150Parameters:
        registered = self._parameters_by_version.get(parameters.parameter_set_version)
        if registered is not None and parameter_fingerprint(parameters) != parameter_fingerprint(
            registered
        ):
            raise ValueError("registered parameter payload mismatch")
        return parameters


SWING_W150_PARAMETER_REGISTRY = ParameterRegistry((SwingW150Parameters(),))
