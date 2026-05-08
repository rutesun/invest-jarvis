from src.tools.technical.models import (
    ExecutionLevelView,
    InvalidationLevelView,
    LevelPayload,
    PriceLevels,
    StructureLevelsPayloadV2,
    StructureLevelView,
    StructureZone,
    StructureZoneSet,
)
from src.tools.technical.price_levels import select_execution_levels


_BALANCE_MAX_DISPLAY_COUNT = 3
_BALANCE_MIN_DISTANCE_ATR_MULTIPLIER = 1.0


def _to_structure_level(zone: StructureZone) -> StructureLevelView:
    reasons = zone.reasons or []
    if zone.reason_codes and not reasons:
        reasons = zone.reason_codes
    return StructureLevelView(
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
        mid_price=zone.mid_price,
        strength=zone.strength,
        reasons=reasons,
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
            label = (
                f"{_format_zone_label(zone.lower_bound, zone.upper_bound)} + "
                f"{reason.split(' fallback')[0]} 하향 이탈"
            )
            break

    reference = None
    reasons = zone.reasons or zone.reason_codes
    if reasons:
        reference = reasons[0]

    return InvalidationLevelView(
        label=label,
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
        reference=reference,
        reasons=reasons,
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


def _zone_contains_price(lower_bound: float, upper_bound: float, price: float) -> bool:
    return lower_bound <= price <= upper_bound


def _pick_primary_label(
    *,
    zone_set: StructureZoneSet,
    current_price: float,
    active_box: StructureLevelView | None,
    support_zones: list[StructureLevelView],
    resistance_zones: list[StructureLevelView],
    former_levels: list[StructureLevelView],
) -> str:
    if zone_set.no_clear_structure:
        return "no_clear_structure"
    if active_box and _zone_contains_price(
        active_box.lower_bound, active_box.upper_bound, current_price
    ):
        return "active_box"
    if support_zones:
        return "support_zone"
    if resistance_zones:
        return "resistance_zone"
    if former_levels:
        return "former_supply_box"
    return "no_clear_structure"


def _build_headline_and_why(
    *,
    summary_label: str,
    active_box: StructureLevelView | None,
    support_zones: list[StructureLevelView],
    resistance_zones: list[StructureLevelView],
    no_clear_reason_codes: list[str],
) -> tuple[str, str]:
    if summary_label == "no_clear_structure":
        reason = ", ".join(no_clear_reason_codes) if no_clear_reason_codes else "근거 점수 약함"
        return "구조 해석 보류", f"최근 구조 신호가 약해 보류 ({reason})"
    if summary_label == "active_box" and active_box:
        return (
            f"박스 중심 구조 {active_box.lower_bound:.2f}~{active_box.upper_bound:.2f}",
            "현재 가격이 박스 내부에 있어 상·하단 반응 확인이 우선",
        )
    if summary_label == "support_zone" and support_zones:
        zone = support_zones[0]
        return (
            f"핵심 지지 존 {zone.lower_bound:.2f}~{zone.upper_bound:.2f}",
            "최근 지지 반응이 상대적으로 강해 하단 방어 확인이 핵심",
        )
    if summary_label == "resistance_zone" and resistance_zones:
        zone = resistance_zones[0]
        return (
            f"핵심 저항 존 {zone.lower_bound:.2f}~{zone.upper_bound:.2f}",
            "상단 매물대 반응이 남아 있어 돌파 확인이 핵심",
        )
    return "구조 혼합", "지지/저항 근거가 혼재해 보조 신호로 해석"


def _is_execution_overlapping_structure(
    *,
    level_price: float,
    zones: list[StructureLevelView],
) -> bool:
    return any(zone.lower_bound <= level_price <= zone.upper_bound for zone in zones)


def _dedupe_execution_levels(
    *,
    execution_levels: list[ExecutionLevelView],
    structure_levels: StructureLevelsPayloadV2,
) -> list[ExecutionLevelView]:
    structure_ranges: list[StructureLevelView] = [
        *structure_levels.support_zones,
        *structure_levels.resistance_zones,
        *structure_levels.former_levels,
    ]
    if structure_levels.active_box:
        structure_ranges.append(structure_levels.active_box)

    deduped: list[ExecutionLevelView] = []
    for level in execution_levels:
        if _is_execution_overlapping_structure(level_price=level.price, zones=structure_ranges):
            continue
        deduped.append(level)
    return deduped


def _build_structure_summary(structure_levels: StructureLevelsPayloadV2) -> str:
    invalidation = structure_levels.invalidation.label if structure_levels.invalidation else "없음"
    return (
        f"{structure_levels.headline} | 지지 {len(structure_levels.support_zones)}개, "
        f"저항 {len(structure_levels.resistance_zones)}개, "
        f"전환 {len(structure_levels.former_levels)}개, 무효화 {invalidation}"
    )


def _build_execution_summary(execution_levels: list[ExecutionLevelView]) -> str:
    if not execution_levels:
        return "실행 레벨 없음"
    return ", ".join(
        f"{level.description} ${level.price:.2f} ({level.distance_pct:+.1f}%)"
        for level in execution_levels
    )


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

    support_zones = [_to_structure_level(zone) for zone in zone_set.demand_zones[:2]]
    raw_supply = [_to_structure_level(zone) for zone in zone_set.supply_zones[:2]]
    balance_zones = _select_balance_for_display(zone_set.balance_zones, atr)
    active_box = _to_structure_level(balance_zones[0]) if balance_zones else None
    current_price = price_levels.current_price

    resistance_zones = [zone for zone in raw_supply if zone.upper_bound >= current_price]
    former_levels = [zone for zone in raw_supply if zone.upper_bound < current_price]

    summary_label = _pick_primary_label(
        zone_set=zone_set,
        current_price=current_price,
        active_box=active_box,
        support_zones=support_zones,
        resistance_zones=resistance_zones,
        former_levels=former_levels,
    )
    headline, why = _build_headline_and_why(
        summary_label=summary_label,
        active_box=active_box,
        support_zones=support_zones,
        resistance_zones=resistance_zones,
        no_clear_reason_codes=zone_set.no_clear_structure_reason_codes,
    )

    structure_levels = StructureLevelsPayloadV2(
        summary_label=summary_label,
        headline=headline,
        why=why,
        active_box=active_box,
        support_zones=support_zones,
        resistance_zones=resistance_zones,
        former_levels=former_levels,
        invalidation=_build_invalidation(zone_set.invalidation_zone),
        patterns_reference=[],
    )

    deduped_execution_levels = _dedupe_execution_levels(
        execution_levels=execution_levels,
        structure_levels=structure_levels,
    )

    return LevelPayload(
        structure_levels=structure_levels,
        execution_levels=deduped_execution_levels,
        structure_summary=_build_structure_summary(structure_levels),
        execution_summary=_build_execution_summary(deduped_execution_levels),
    )
