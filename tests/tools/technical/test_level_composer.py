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

    assert payload.structure_levels.support_zones[0].lower_bound == 200.0
    assert payload.structure_levels.support_zones[0].upper_bound == 205.0
    assert payload.structure_levels.summary_label == "support_zone"
    assert payload.execution_levels[0].type == "pivot_r1"
    assert payload.structure_levels.invalidation is not None
    assert payload.structure_levels.invalidation.label == "200.00~205.00 하향 이탈"
    assert payload.structure_summary
    assert payload.execution_summary


def test_compose_level_payload_sets_active_box_from_balance_zone():
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
    price_levels = PriceLevels(current_price=100.0)

    payload = compose_level_payload(zone_set, price_levels, atr=1.0)

    assert payload.structure_levels.active_box is not None
    assert payload.structure_levels.active_box.lower_bound == 99.0
    assert payload.structure_levels.active_box.upper_bound == 101.0
    assert payload.structure_levels.summary_label == "active_box"


def test_compose_level_payload_dedupes_execution_levels_inside_structure_ranges():
    from src.tools.technical.level_composer import compose_level_payload

    demand = StructureZone(
        zone_type="demand",
        lower_bound=95.0,
        upper_bound=97.0,
        mid_price=96.0,
        touch_count=3,
        last_touch_date="2026-05-01",
        touch_score=3.0,
        recency_score=5.0,
        volume_reaction_score=2.0,
        confluence_score=0.5,
        total_score=8.0,
        strength="core",
        reasons=["demand"],
    )
    zone_set = StructureZoneSet(
        demand_zones=[demand],
        supply_zones=[],
        invalidation_candidates=[demand],
        invalidation_zone=demand,
        all_candidates=[demand],
    )
    price_levels = PriceLevels(
        current_price=100.0,
        support_levels=[
            PriceLevel(price=96.0, type="pivot_s1", distance_pct=-4.0, description="피봇 S1"),
            PriceLevel(price=92.0, type="sma_50", distance_pct=-8.0, description="50일선"),
        ],
    )

    payload = compose_level_payload(zone_set, price_levels)

    assert [level.type for level in payload.execution_levels] == ["sma_50"]


def test_compose_level_payload_prefers_trace_selected_label_for_consistency():
    from src.tools.technical.level_composer import compose_level_payload

    support = StructureZone(
        zone_type="demand",
        lower_bound=90.0,
        upper_bound=95.0,
        mid_price=92.5,
        touch_count=2,
        last_touch_date="2026-05-01",
        touch_score=2.0,
        recency_score=5.0,
        volume_reaction_score=2.0,
        confluence_score=0.0,
        total_score=6.0,
        strength="core",
        reasons=["support"],
    )
    resistance = StructureZone(
        zone_type="supply",
        lower_bound=105.0,
        upper_bound=110.0,
        mid_price=107.5,
        touch_count=4,
        last_touch_date="2026-05-02",
        touch_score=4.0,
        recency_score=5.0,
        volume_reaction_score=3.0,
        confluence_score=0.0,
        total_score=9.0,
        strength="core",
        reasons=["resistance"],
    )
    zone_set = StructureZoneSet(
        demand_zones=[support],
        supply_zones=[resistance],
        selection_trace=[{"selected_label": "support_zone"}],
        invalidation_candidates=[],
        invalidation_zone=support,
        all_candidates=[support, resistance],
    )
    payload = compose_level_payload(zone_set, PriceLevels(current_price=100.0))

    assert payload.structure_levels.summary_label == "support_zone"
