from src.tools.technical.models import (
    ExecutionLevelView,
    InvalidationLevelView,
    LevelPayload,
    PriceLevels,
    StructureLevelsPayload,
    StructureLevelView,
    StructureZone,
    StructureZoneSet,
)
from src.tools.technical.price_levels import select_execution_levels


_BALANCE_MAX_DISPLAY_COUNT = 3
_BALANCE_MIN_DISTANCE_ATR_MULTIPLIER = 1.0


def _to_structure_level(zone: StructureZone) -> StructureLevelView:
    return StructureLevelView(
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
        mid_price=zone.mid_price,
        strength=zone.strength,
        reasons=zone.reasons,
        touch_count=zone.touch_count,
        last_touch_date=zone.last_touch_date,
        total_score=zone.total_score,
    )


def _format_zone_label(lower_bound: float, upper_bound: float) -> str:
    return f"{lower_bound:.2f}~{upper_bound:.2f}"


def _build_invalidation(zone: StructureZone | None) -> InvalidationLevelView | None:
    if zone is None:
        return None

    label = f"{_format_zone_label(zone.lower_bound, zone.upper_bound)} 하향 이탈"
    for reason in zone.reasons:
        if "150일선" in reason or "200일선" in reason:
            label = f"{_format_zone_label(zone.lower_bound, zone.upper_bound)} + {reason.split(' fallback')[0]} 하향 이탈"
            break

    reference = None
    if zone.reasons:
        reference = zone.reasons[0]

    return InvalidationLevelView(
        label=label,
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
        reference=reference,
        reasons=zone.reasons,
    )


def _build_structure_summary(structure_levels: StructureLevelsPayload) -> str:
    demand_count = len(structure_levels.demand_zones)
    supply_count = len(structure_levels.supply_zones)
    balance_count = len(structure_levels.balance_zones)
    invalidation = structure_levels.invalidation.label if structure_levels.invalidation else "없음"
    return (
        f"수요 존 {demand_count}개, 공급 존 {supply_count}개, "
        f"밸런스 존 {balance_count}개, 무효화 기준 {invalidation}"
    )


def _build_execution_summary(execution_levels: list[ExecutionLevelView]) -> str:
    if not execution_levels:
        return "실행 레벨 없음"
    return ", ".join(
        f"{level.description} ${level.price:.2f} ({level.distance_pct:+.1f}%)"
        for level in execution_levels
    )


def _zone_width(zone: StructureZone) -> float:
    return max(zone.upper_bound - zone.lower_bound, 1e-6)


def _required_balance_distance(
    left: StructureZone,
    right: StructureZone,
    atr: float | None,
) -> float:
    if atr and atr > 0:
        return atr * _BALANCE_MIN_DISTANCE_ATR_MULTIPLIER
    return min(_zone_width(left), _zone_width(right)) * 0.5


def _select_balance_for_display(
    zones: list[StructureZone],
    atr: float | None,
) -> list[StructureZone]:
    if not zones:
        return []

    ordered = sorted(zones, key=lambda zone: zone.total_score, reverse=True)
    selected: list[StructureZone] = []
    for candidate in ordered:
        if any(
            abs(candidate.mid_price - chosen.mid_price)
            < _required_balance_distance(candidate, chosen, atr)
            for chosen in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= _BALANCE_MAX_DISPLAY_COUNT:
            break

    return selected


def compose_level_payload(
    zone_set: StructureZoneSet,
    price_levels: PriceLevels,
    atr: float | None = None,
) -> LevelPayload:
    execution_levels = [
        ExecutionLevelView(
            type=level.type,
            description=level.description,
            price=level.price,
            distance_pct=level.distance_pct,
        )
        for level in select_execution_levels(price_levels, max_count=3)
    ]
    structure_levels = StructureLevelsPayload(
        demand_zones=[_to_structure_level(zone) for zone in zone_set.demand_zones[:2]],
        supply_zones=[_to_structure_level(zone) for zone in zone_set.supply_zones[:2]],
        balance_zones=[
            _to_structure_level(zone)
            for zone in _select_balance_for_display(zone_set.balance_zones, atr)
        ],
        invalidation=_build_invalidation(zone_set.invalidation_zone),
    )
    return LevelPayload(
        structure_levels=structure_levels,
        execution_levels=execution_levels,
        structure_summary=_build_structure_summary(structure_levels),
        execution_summary=_build_execution_summary(execution_levels),
    )
