from src.tools.technical.models import PriceLevels, StructureZone, StructureZoneSet
from src.tools.technical.price_levels import select_execution_levels


def _format_zone(zone: StructureZone) -> str:
    return f"{zone.lower_bound:.2f}~{zone.upper_bound:.2f}"


def _format_invalidation(zone: StructureZone | None) -> str | None:
    if zone is None:
        return None
    return f"{zone.lower_bound:.2f} 하향 이탈"


def compose_level_payload(zone_set: StructureZoneSet, price_levels: PriceLevels) -> dict:
    execution_levels = select_execution_levels(price_levels, max_count=3)
    return {
        "structure_levels": {
            "demand_zones": [_format_zone(zone) for zone in zone_set.demand_zones[:2]],
            "supply_zones": [_format_zone(zone) for zone in zone_set.supply_zones[:2]],
            "invalidation": _format_invalidation(zone_set.invalidation_zone),
        },
        "execution_levels": [
            {
                "type": level.type,
                "description": level.description,
                "price": level.price,
                "distance_pct": level.distance_pct,
            }
            for level in execution_levels
        ],
    }
