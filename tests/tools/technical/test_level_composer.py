from src.tools.technical.models import PriceLevel, PriceLevels, StructureZone, StructureZoneSet


def test_compose_level_payload_prefers_structure_then_execution():
    from src.tools.technical.level_composer import compose_level_payload

    demand = StructureZone(
        zone_type="demand",
        lower_bound=200.0,
        upper_bound=205.0,
        mid_price=202.5,
        touch_count=4,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=4.0,
        volume_reaction_score=3.0,
        confluence_score=2.0,
        total_score=13.0,
        strength="core",
        reasons=["반복 지지"],
    )
    zone_set = StructureZoneSet(
        demand_zones=[demand],
        supply_zones=[],
        invalidation_candidates=[demand],
        invalidation_zone=demand,
        all_candidates=[demand],
    )
    price_levels = PriceLevels(
        current_price=210.0,
        support_levels=[
            PriceLevel(price=205.0, type="pivot_s1", distance_pct=-2.3, description="피봇 지지1"),
            PriceLevel(price=198.0, type="sma_50", distance_pct=-5.7, description="50일선"),
        ],
        resistance_levels=[
            PriceLevel(price=218.0, type="pivot_r1", distance_pct=3.8, description="피봇 저항1"),
        ],
    )

    payload = compose_level_payload(zone_set, price_levels)

    assert payload["structure_levels"]["demand_zones"][0] == "200.00~205.00"
    assert payload["execution_levels"][0]["type"] == "pivot_s1"
    assert payload["structure_levels"]["invalidation"] == "200.00 하향 이탈"
