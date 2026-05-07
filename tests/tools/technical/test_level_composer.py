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

    assert payload.structure_levels.demand_zones[0].lower_bound == 200.0
    assert payload.structure_levels.demand_zones[0].upper_bound == 205.0
    assert payload.execution_levels[0].type == "pivot_s1"
    assert payload.structure_levels.invalidation is not None
    assert payload.structure_levels.invalidation.label == "200.00~205.00 하향 이탈"
    assert payload.structure_summary
    assert payload.execution_summary


def test_compose_level_payload_limits_balance_to_three_and_hides_near_duplicates():
    from src.tools.technical.level_composer import compose_level_payload

    balance_1 = StructureZone(
        zone_type="balance",
        lower_bound=99.0,
        upper_bound=101.0,
        mid_price=100.0,
        touch_count=8,
        last_touch_date="2026-05-01",
        touch_score=8.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=9.0,
        strength="core",
        reasons=["b1"],
    )
    balance_2 = StructureZone(
        zone_type="balance",
        lower_bound=99.6,
        upper_bound=101.6,
        mid_price=100.6,
        touch_count=7,
        last_touch_date="2026-05-01",
        touch_score=7.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=8.8,
        strength="core",
        reasons=["b2"],
    )
    balance_3 = StructureZone(
        zone_type="balance",
        lower_bound=101.5,
        upper_bound=103.5,
        mid_price=102.5,
        touch_count=6,
        last_touch_date="2026-05-01",
        touch_score=6.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=8.5,
        strength="core",
        reasons=["b3"],
    )
    balance_4 = StructureZone(
        zone_type="balance",
        lower_bound=104.0,
        upper_bound=106.0,
        mid_price=105.0,
        touch_count=5,
        last_touch_date="2026-05-01",
        touch_score=5.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=8.0,
        strength="core",
        reasons=["b4"],
    )

    zone_set = StructureZoneSet(
        demand_zones=[],
        supply_zones=[],
        balance_zones=[balance_1, balance_2, balance_3, balance_4],
        invalidation_candidates=[],
        invalidation_zone=None,
        all_candidates=[balance_1, balance_2, balance_3, balance_4],
    )
    price_levels = PriceLevels(current_price=103.0)

    payload = compose_level_payload(zone_set, price_levels, atr=1.0)
    centers = [zone.mid_price for zone in payload.structure_levels.balance_zones]

    assert len(payload.structure_levels.balance_zones) == 3
    assert 100.0 in centers
    assert 100.6 not in centers
