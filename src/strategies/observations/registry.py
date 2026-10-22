"""고정 Observation vocabulary와 lifecycle 계약. detector 실행은 소유하지 않는다."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from src.strategies.models import (
    ObservationCode,
    ObservationDirection,
    ObservationKind,
    ObservationScope,
    ObservationTemporalType,
)


@dataclass(frozen=True)
class ObservationDefinition:
    code: ObservationCode
    kind: ObservationKind
    direction: ObservationDirection
    scopes: frozenset[ObservationScope]
    temporal_type: ObservationTemporalType
    start: str
    maintain: str
    end: str
    reentry: str
    source_dependency: Literal["NONE", "OPTIONAL", "REQUIRED"]
    anchor_dependency: Literal["NONE", "OPTIONAL", "REQUIRED"]
    detector_validity: Literal["IMPLEMENTED", "NOT_IMPLEMENTED", "UNRESOLVED"]
    predictive_usefulness: Literal["UNRESOLVED"] = "UNRESOLVED"


def _definition(
    code: ObservationCode,
    direction: ObservationDirection,
    temporal_type: ObservationTemporalType,
    *,
    start: str,
    maintain: str,
    end: str,
    reentry: str,
    source: Literal["NONE", "OPTIONAL", "REQUIRED"] = "NONE",
    anchor: Literal["NONE", "OPTIONAL", "REQUIRED"] = "NONE",
    setup: bool = False,
    entry_only: bool = False,
) -> ObservationDefinition:
    return ObservationDefinition(
        code=code,
        kind=ObservationKind.SETUP if setup else ObservationKind.EVIDENCE,
        direction=direction,
        scopes=frozenset({ObservationScope.ENTRY})
        if setup or entry_only
        else frozenset({ObservationScope.ENTRY, ObservationScope.POSITION}),
        temporal_type=temporal_type,
        start=start,
        maintain=maintain,
        end=end,
        reentry=reentry,
        source_dependency=source,
        anchor_dependency=anchor,
        detector_validity=(
            "UNRESOLVED"
            if code
            in {
                ObservationCode.VOLUME_CONTRACTION,
                ObservationCode.UP_VOLUME_EXPANSION,
                ObservationCode.DOWN_VOLUME_EXPANSION,
            }
            else "IMPLEMENTED"
        ),
    )


_definitions = [
    _definition(
        ObservationCode.PULLBACK_WATCH,
        ObservationDirection.NEUTRAL,
        ObservationTemporalType.EPISODE,
        setup=True,
        anchor="REQUIRED",
        start="support test qualifies as a pullback watch",
        maintain="same support test remains eligible",
        end="reversal signal, support invalidation or expiry",
        reentry="new qualifying watch origin; prior completed bar required for reversal",
    ),
    _definition(
        ObservationCode.POST_OVERHEAT_RECOVERY_WATCH,
        ObservationDirection.NEUTRAL,
        ObservationTemporalType.EPISODE,
        setup=True,
        start="overheated phase enters correction",
        maintain="corrected phase awaits recovery",
        end="recovery signal, invalidation or expiry",
        reentry="new overheat correction origin",
    ),
]
for _code in (
    ObservationCode.HIGHER_LOW,
    ObservationCode.HIGHER_HIGH,
    ObservationCode.LOWER_HIGH,
    ObservationCode.LOWER_LOW,
):
    _definitions.append(
        _definition(
            _code,
            ObservationDirection.POSITIVE
            if _code in (ObservationCode.HIGHER_LOW, ObservationCode.HIGHER_HIGH)
            else ObservationDirection.RISK,
            ObservationTemporalType.EVENT,
            start="same-type pivot relation becomes confirmed on confirmation bar",
            maintain="single confirmed event",
            end="resolved on confirmation bar",
            reentry="each distinct same-type confirmed pivot",
        )
    )
for _code in (ObservationCode.BREAKOUT_RECLAIM, ObservationCode.SUPPORT_RECLAIM):
    _definitions.append(
        _definition(
            _code,
            ObservationDirection.POSITIVE,
            ObservationTemporalType.EVENT,
            source="REQUIRED" if _code is ObservationCode.BREAKOUT_RECLAIM else "OPTIONAL",
            anchor="REQUIRED",
            start="previously breached anchor is reclaimed",
            maintain="single reclaim event; source terminal state is context",
            end="resolved on reclaim bar without reviving terminal opportunity",
            reentry="new breach then reclaim for the same anchor",
        )
    )
_definitions.append(
    _definition(
        ObservationCode.VOLUME_CONTRACTION,
        ObservationDirection.POSITIVE,
        ObservationTemporalType.EPISODE,
        entry_only=True,
        start="volume enters selected contraction condition",
        maintain="contraction condition persists",
        end="contraction condition ends",
        reentry="new contraction episode after prior condition ends",
    )
)
for _code in (ObservationCode.UP_VOLUME_EXPANSION, ObservationCode.DOWN_VOLUME_EXPANSION):
    _definitions.append(
        _definition(
            _code,
            ObservationDirection.POSITIVE
            if _code is ObservationCode.UP_VOLUME_EXPANSION
            else ObservationDirection.RISK,
            ObservationTemporalType.EVENT,
            start="directional return and volume meet selected expansion condition",
            maintain="single bar event",
            end="resolved on observed bar",
            reentry="each qualifying directional expansion bar",
        )
    )
_definitions.append(
    _definition(
        ObservationCode.MOMENTUM_REACCELERATION,
        ObservationDirection.POSITIVE,
        ObservationTemporalType.EVENT,
        start="selected momentum formula turns upward",
        maintain="single turn event",
        end="resolved on turn bar",
        reentry="new upward turn after prior condition ends",
    )
)
for _code in (
    ObservationCode.BREAKOUT_LEVEL_BREACH,
    ObservationCode.SUPPORT_BREAK,
    ObservationCode.PULLBACK_LOW_BREACH,
):
    _definitions.append(
        _definition(
            _code,
            ObservationDirection.RISK,
            ObservationTemporalType.EPISODE,
            source="OPTIONAL" if _code is ObservationCode.SUPPORT_BREAK else "REQUIRED",
            anchor="REQUIRED",
            start="selected break condition breaches the associated anchor",
            maintain="anchor remains breached; frozen failure latch is separate",
            end="reclaim or support test termination",
            reentry="new anchor-test or new breach after reclaim",
        )
    )
_definitions.append(
    _definition(
        ObservationCode.MOMENTUM_DECELERATION,
        ObservationDirection.RISK,
        ObservationTemporalType.EPISODE,
        start="selected momentum deceleration condition begins",
        maintain="deceleration condition persists",
        end="deceleration condition ends",
        reentry="new deceleration episode after prior condition ends",
    )
)

OBSERVATION_REGISTRY = MappingProxyType({item.code: item for item in _definitions})
