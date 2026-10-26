"""Observation 전용 설정. 미선정 값은 None으로 남기며 매매 설정과 분리한다."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal

from src.storage.canonical import canonical_bytes


@dataclass(frozen=True)
class ObservationParameters:
    version: str = "OBSERVATION_PARAMS_V1"
    up_volume_ratio: float | None = None
    down_volume_ratio: float | None = None
    contraction_ratio: float | None = None
    break_buffer_atr: float | None = None
    reclaim_buffer_atr: float | None = None
    reacceleration_mode: (
        Literal["SMA20_TURN", "SMA20_TURN_POSITIVE_RETURN", "SMA20_TURN_HIGH_BREAK"] | None
    ) = None
    zone_distance_atr: float | None = None

    def __post_init__(self) -> None:
        for name in ("up_volume_ratio", "down_volume_ratio", "contraction_ratio"):
            value = getattr(self, name)
            if value is not None and (not isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be positive or None")
        for name in ("break_buffer_atr", "reclaim_buffer_atr", "zone_distance_atr"):
            value = getattr(self, name)
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f"{name} must be nonnegative or None")
        if self.reacceleration_mode not in (
            None,
            "SMA20_TURN",
            "SMA20_TURN_POSITIVE_RETURN",
            "SMA20_TURN_HIGH_BREAK",
        ):
            raise ValueError("unknown reacceleration_mode")

    @property
    def parameter_fingerprint(self) -> str:
        return hashlib.sha256(canonical_bytes(asdict(self))).hexdigest()


# 승인된 표시 설정만 제품 Adapter에서 선택한다. schema와 기존 SETUP 기본값은 보존한다.
PRODUCT_OBSERVATION_PARAMETERS = ObservationParameters(
    break_buffer_atr=0.0,
    reclaim_buffer_atr=0.0,
    reacceleration_mode="SMA20_TURN",
    zone_distance_atr=0.5,
)
