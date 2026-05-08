import pandas as pd

from src.tools.technical.models import (
    IndicatorSnapshot,
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
    ZoneTestArtifact,
)
from src.tools.technical.structure_zones import (
    StructureZoneDetector,
    calculate_zone_half_width,
    cluster_price_candidates,
)


def test_structure_zone_set_keeps_invalidation_candidates():
    zone = StructureZone(
        zone_type="demand",
        lower_bound=100.0,
        upper_bound=105.0,
        mid_price=102.5,
        touch_count=3,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=3.0,
        volume_reaction_score=2.0,
        confluence_score=1.0,
        total_score=10.0,
        strength="core",
        reasons=["반복 터치"],
    )

    zone_set = StructureZoneSet(
        demand_zones=[zone],
        supply_zones=[],
        invalidation_candidates=[zone],
        invalidation_zone=zone,
        all_candidates=[zone],
    )

    assert zone_set.invalidation_candidates[0].zone_type == "demand"


def test_zone_test_artifact_has_schema_version():
    artifact = ZoneTestArtifact(
        schema_version="v1",
        symbol="ALAB",
        csv_path="tests/fixtures/technical/structure_zones/ALAB.csv",
        params={"top_n_per_side": 2},
        candidates=[],
        selected_zones=[],
        score_breakdown=[],
    )

    assert artifact.schema_version == "v1"


def test_structure_zone_config_defaults_are_explicit():
    config = StructureZoneConfig()

    assert config.top_n_per_side == 5
    assert config.min_zone_width_pct > 0
    assert config.selection_max_distance_pct > 0


def test_calculate_zone_half_width_respects_pct_floor_and_ceiling():
    width = calculate_zone_half_width(price=100.0, atr=1.0, config=StructureZoneConfig())

    assert width >= 1.0
    assert width <= 5.0


def test_score_confluence_includes_volume_profile_overlap():
    detector = StructureZoneDetector()
    dates = pd.date_range("2026-01-01", periods=12, freq="D")
    df = pd.DataFrame(
        {
            "Open": [99, 100, 101, 102, 103, 102, 101, 100, 102, 103, 104, 105],
            "High": [100, 101, 102, 103, 104, 103, 102, 101, 103, 104, 105, 106],
            "Low": [98, 99, 100, 101, 102, 101, 100, 99, 101, 102, 103, 104],
            "Close": [99, 100, 101, 102, 103, 102, 101, 100, 102, 103, 104, 105],
            "Volume": [
                100_000,
                120_000,
                140_000,
                2_000_000,
                180_000,
                1_800_000,
                150_000,
                130_000,
                1_600_000,
                160_000,
                150_000,
                140_000,
            ],
        },
        index=dates,
    )
    snapshot = IndicatorSnapshot(price=105.0, change_pct=0.0, atr=2.0)

    no_overlap_score = detector._score_confluence([95.0, 96.0], snapshot, df)
    overlap_score = detector._score_confluence([101.5, 102.5], snapshot, df)

    assert overlap_score > no_overlap_score


def test_cluster_price_candidates_groups_nearby_swings():
    clusters = cluster_price_candidates([100.0, 101.0, 118.0], half_width=2.0)

    assert clusters == [[100.0, 101.0], [118.0]]


def test_cluster_price_candidates_breaks_chain_when_center_is_far():
    clusters = cluster_price_candidates([60.0, 69.0, 78.0], half_width=10.0)

    assert clusters == [[60.0, 69.0], [78.0]]


def test_cluster_price_candidates_respects_span_cap():
    clusters = cluster_price_candidates(
        [60.0, 65.0, 70.0, 75.0, 80.0],
        half_width=10.0,
        span_cap_multiplier=1.4,
    )

    assert clusters == [[60.0, 65.0, 70.0], [75.0, 80.0]]


def test_detector_sorts_demand_zones_by_total_score():
    dates = pd.date_range("2025-01-01", periods=220, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100 + (i % 5) for i in range(220)],
            "High": [102 + (i % 5) for i in range(220)],
            "Low": [98 + (i % 5) for i in range(220)],
            "Close": [100 + (i % 5) for i in range(220)],
            "Volume": [1_000_000 + i * 1000 for i in range(220)],
        },
        index=dates,
    )
    snapshot = IndicatorSnapshot(price=104.0, change_pct=1.0, atr=3.0, sma_150=95.0)

    result = StructureZoneDetector().detect(df, snapshot)

    assert result.demand_zones == sorted(
        result.demand_zones,
        key=lambda zone: zone.total_score,
        reverse=True,
    )


def test_detector_tie_break_prefers_recent_touch_then_touch_count():
    snapshot = IndicatorSnapshot(price=104.0, change_pct=1.0, atr=3.0, sma_150=95.0)
    detector = StructureZoneDetector()

    older = StructureZone(
        zone_type="demand",
        lower_bound=95.0,
        upper_bound=98.0,
        mid_price=96.5,
        touch_count=4,
        last_touch_date="2025-06-01",
        touch_score=4.0,
        recency_score=3.0,
        volume_reaction_score=2.0,
        confluence_score=1.0,
        total_score=10.0,
        strength="core",
        reasons=["older"],
    )
    newer = StructureZone(
        zone_type="demand",
        lower_bound=99.0,
        upper_bound=101.0,
        mid_price=100.0,
        touch_count=2,
        last_touch_date="2025-08-01",
        touch_score=4.0,
        recency_score=3.0,
        volume_reaction_score=2.0,
        confluence_score=1.0,
        total_score=10.0,
        strength="core",
        reasons=["newer"],
    )

    ordered = detector._sort_zones([older, newer], snapshot.price)

    assert ordered[0].last_touch_date == "2025-08-01"


def test_select_with_guard_prioritizes_recent_and_nearby_zones():
    detector = StructureZoneDetector(
        StructureZoneConfig(
            top_n_per_side=2,
            selection_max_distance_pct=0.2,
            selection_min_recency_score=3.0,
        )
    )
    current_price = 100.0
    far_old = StructureZone(
        zone_type="demand",
        lower_bound=40.0,
        upper_bound=50.0,
        mid_price=45.0,
        touch_count=20,
        last_touch_date="2025-01-01",
        touch_score=20.0,
        recency_score=1.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=15.0,
        strength="core",
        reasons=["far old"],
    )
    near_recent = StructureZone(
        zone_type="demand",
        lower_bound=92.0,
        upper_bound=98.0,
        mid_price=95.0,
        touch_count=5,
        last_touch_date="2026-04-20",
        touch_score=5.0,
        recency_score=5.0,
        volume_reaction_score=3.0,
        confluence_score=0.0,
        total_score=8.0,
        strength="core",
        reasons=["near recent"],
    )
    near_recent_2 = StructureZone(
        zone_type="demand",
        lower_bound=101.0,
        upper_bound=106.0,
        mid_price=103.5,
        touch_count=4,
        last_touch_date="2026-04-19",
        touch_score=4.0,
        recency_score=5.0,
        volume_reaction_score=3.0,
        confluence_score=0.0,
        total_score=7.0,
        strength="core",
        reasons=["near recent 2"],
    )

    sorted_zones = [far_old, near_recent, near_recent_2]
    selected = detector._select_with_guard(
        sorted_zones,
        current_price,
        zone_type="demand",
        max_count=2,
    )

    assert selected[0].reasons[0] == "near recent"
    assert selected[1].reasons[0] == "near recent 2"


def test_select_with_guard_backfills_when_filtered_candidates_are_insufficient():
    detector = StructureZoneDetector(
        StructureZoneConfig(
            top_n_per_side=2,
            selection_max_distance_pct=0.05,
            selection_min_recency_score=5.0,
        )
    )
    current_price = 100.0
    near_recent = StructureZone(
        zone_type="supply",
        lower_bound=102.0,
        upper_bound=104.0,
        mid_price=103.0,
        touch_count=3,
        last_touch_date="2026-04-20",
        touch_score=3.0,
        recency_score=5.0,
        volume_reaction_score=2.0,
        confluence_score=0.0,
        total_score=6.0,
        strength="core",
        reasons=["near recent"],
    )
    far_old = StructureZone(
        zone_type="supply",
        lower_bound=150.0,
        upper_bound=160.0,
        mid_price=155.0,
        touch_count=10,
        last_touch_date="2025-01-01",
        touch_score=10.0,
        recency_score=1.0,
        volume_reaction_score=4.0,
        confluence_score=0.0,
        total_score=9.0,
        strength="core",
        reasons=["far old"],
    )

    selected = detector._select_with_guard(
        [near_recent, far_old],
        current_price,
        zone_type="supply",
        max_count=2,
    )

    assert len(selected) == 2
    assert selected[0].reasons[0] == "near recent"
    assert selected[1].reasons[0] == "far old"


def test_select_with_guard_for_supply_prefers_zones_above_current_price():
    detector = StructureZoneDetector(StructureZoneConfig(top_n_per_side=1))
    current_price = 100.0
    absorbed_supply = StructureZone(
        zone_type="supply",
        lower_bound=70.0,
        upper_bound=80.0,
        mid_price=75.0,
        touch_count=12,
        last_touch_date="2026-05-01",
        touch_score=12.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=9.5,
        strength="core",
        reasons=["absorbed"],
    )
    active_supply = StructureZone(
        zone_type="supply",
        lower_bound=110.0,
        upper_bound=120.0,
        mid_price=115.0,
        touch_count=6,
        last_touch_date="2026-05-01",
        touch_score=6.0,
        recency_score=5.0,
        volume_reaction_score=4.0,
        confluence_score=0.0,
        total_score=6.5,
        strength="core",
        reasons=["active"],
    )

    selected = detector._select_with_guard(
        [absorbed_supply, active_supply],
        current_price,
        zone_type="supply",
        max_count=1,
    )

    assert selected[0].reasons[0] == "active"


def test_select_with_guard_for_demand_prefers_zones_not_above_current_price():
    detector = StructureZoneDetector(StructureZoneConfig(top_n_per_side=1))
    current_price = 100.0
    broken_demand = StructureZone(
        zone_type="demand",
        lower_bound=112.0,
        upper_bound=120.0,
        mid_price=116.0,
        touch_count=10,
        last_touch_date="2026-05-01",
        touch_score=10.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=8.5,
        strength="core",
        reasons=["broken demand"],
    )
    active_demand = StructureZone(
        zone_type="demand",
        lower_bound=90.0,
        upper_bound=97.0,
        mid_price=93.5,
        touch_count=5,
        last_touch_date="2026-05-01",
        touch_score=5.0,
        recency_score=5.0,
        volume_reaction_score=4.0,
        confluence_score=0.0,
        total_score=6.0,
        strength="core",
        reasons=["active demand"],
    )

    selected = detector._select_with_guard(
        [broken_demand, active_demand],
        current_price,
        zone_type="demand",
        max_count=1,
    )

    assert selected[0].reasons[0] == "active demand"


def test_detect_uses_ma_fallback_when_selected_demand_is_only_above_current_price():
    detector = StructureZoneDetector(StructureZoneConfig(top_n_per_side=1))
    demand_above = StructureZone(
        zone_type="demand",
        lower_bound=112.0,
        upper_bound=120.0,
        mid_price=116.0,
        touch_count=8,
        last_touch_date="2026-05-01",
        touch_score=8.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=8.0,
        strength="core",
        reasons=["only above demand"],
    )
    supply_above = StructureZone(
        zone_type="supply",
        lower_bound=130.0,
        upper_bound=138.0,
        mid_price=134.0,
        touch_count=6,
        last_touch_date="2026-05-01",
        touch_score=6.0,
        recency_score=5.0,
        volume_reaction_score=4.0,
        confluence_score=0.0,
        total_score=6.0,
        strength="core",
        reasons=["supply"],
    )
    detector._build_candidates = lambda _df, _snapshot: [demand_above, supply_above]

    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0, sma_150=95.0)
    result = detector.detect(pd.DataFrame({"Close": [100.0]}), snapshot)

    assert result.invalidation_zone is not None
    assert "fallback" in " ".join(result.invalidation_zone.reasons)


def test_detect_promotes_above_current_demand_as_supply_candidate():
    detector = StructureZoneDetector(StructureZoneConfig(top_n_per_side=1))
    broken_demand = StructureZone(
        zone_type="demand",
        lower_bound=121.0,
        upper_bound=126.0,
        mid_price=123.5,
        touch_count=7,
        last_touch_date="2026-05-01",
        touch_score=7.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=7.2,
        strength="core",
        reasons=["old demand"],
    )
    weak_supply = StructureZone(
        zone_type="supply",
        lower_bound=130.0,
        upper_bound=133.0,
        mid_price=131.5,
        touch_count=3,
        last_touch_date="2026-05-01",
        touch_score=3.0,
        recency_score=5.0,
        volume_reaction_score=3.0,
        confluence_score=0.0,
        total_score=4.0,
        strength="secondary",
        reasons=["supply"],
    )
    detector._build_candidates = lambda _df, _snapshot: [broken_demand, weak_supply]

    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0, sma_150=95.0)
    result = detector.detect(pd.DataFrame({"Close": [100.0]}), snapshot)

    assert result.supply_zones
    assert "전환 저항" in " ".join(result.supply_zones[0].reasons)


def test_merge_overlapping_demand_supply_creates_balance_zone():
    detector = StructureZoneDetector(StructureZoneConfig(top_n_per_side=2))
    demand = StructureZone(
        zone_type="demand",
        lower_bound=10.0,
        upper_bound=12.0,
        mid_price=11.0,
        touch_count=3,
        last_touch_date="2026-04-20",
        touch_score=3.0,
        recency_score=5.0,
        volume_reaction_score=2.0,
        confluence_score=0.5,
        total_score=8.0,
        strength="core",
        reasons=["반복 지지"],
    )
    supply = StructureZone(
        zone_type="supply",
        lower_bound=11.0,
        upper_bound=13.0,
        mid_price=12.0,
        touch_count=2,
        last_touch_date="2026-04-18",
        touch_score=2.0,
        recency_score=5.0,
        volume_reaction_score=2.5,
        confluence_score=0.5,
        total_score=7.0,
        strength="secondary",
        reasons=["반복 저항"],
    )

    kept_demand, kept_supply, balance = detector._merge_overlapping_opposite_zones(
        demand_zones=[demand],
        supply_zones=[supply],
        atr=1.5,
        current_price=12.0,
    )

    assert kept_demand == []
    assert kept_supply == []
    assert len(balance) == 1
    assert balance[0].zone_type == "balance"
    assert "중첩 구간 통합" in " ".join(balance[0].reasons)
    assert balance[0].touch_count == 5


def test_merge_overlapping_demand_supply_keeps_both_when_touch_dates_far():
    detector = StructureZoneDetector(
        StructureZoneConfig(
            overlap_max_last_touch_gap_days=15,
        )
    )
    demand = StructureZone(
        zone_type="demand",
        lower_bound=10.0,
        upper_bound=12.0,
        mid_price=11.0,
        touch_count=3,
        last_touch_date="2026-04-20",
        touch_score=3.0,
        recency_score=5.0,
        volume_reaction_score=2.0,
        confluence_score=0.5,
        total_score=8.0,
        strength="core",
        reasons=["반복 지지"],
    )
    supply = StructureZone(
        zone_type="supply",
        lower_bound=11.0,
        upper_bound=13.0,
        mid_price=12.0,
        touch_count=2,
        last_touch_date="2026-02-01",
        touch_score=2.0,
        recency_score=1.0,
        volume_reaction_score=2.5,
        confluence_score=0.5,
        total_score=7.0,
        strength="secondary",
        reasons=["반복 저항"],
    )

    kept_demand, kept_supply, balance = detector._merge_overlapping_opposite_zones(
        demand_zones=[demand],
        supply_zones=[supply],
        atr=1.5,
        current_price=12.0,
    )

    assert len(kept_demand) == 1
    assert len(kept_supply) == 1
    assert balance == []


def test_merge_balance_zones_collapses_overlapping_ranges():
    detector = StructureZoneDetector(StructureZoneConfig())
    balance_a = StructureZone(
        zone_type="balance",
        lower_bound=9.9,
        upper_bound=11.6,
        mid_price=10.75,
        touch_count=20,
        last_touch_date="2026-03-30",
        touch_score=8.0,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=9.4,
        strength="core",
        reasons=["수요/공급 중첩 구간 통합"],
    )
    balance_b = StructureZone(
        zone_type="balance",
        lower_bound=11.0,
        upper_bound=13.0,
        mid_price=12.0,
        touch_count=25,
        last_touch_date="2026-04-13",
        touch_score=8.2,
        recency_score=5.0,
        volume_reaction_score=5.0,
        confluence_score=0.0,
        total_score=9.3,
        strength="core",
        reasons=["수요/공급 중첩 구간 통합"],
    )

    merged = detector._merge_balance_zones([balance_a, balance_b], atr=0.9)

    assert len(merged) == 1
    assert merged[0].lower_bound == 9.9
    assert merged[0].upper_bound == 13.0
    assert merged[0].touch_count == 45
    assert "밸런스 존 중첩 병합" in merged[0].reasons[0]


def test_choose_invalidation_zone_prefers_core_zone_then_ma_and_swing_low():
    snapshot = IndicatorSnapshot(
        price=200.0,
        change_pct=1.0,
        sma_150=192.0,
        sma_200=190.0,
        swing_low=185.0,
    )
    detector = StructureZoneDetector()
    core_zone = StructureZone(
        zone_type="demand",
        lower_bound=188.0,
        upper_bound=194.0,
        mid_price=191.0,
        touch_count=4,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=5.0,
        volume_reaction_score=3.0,
        confluence_score=1.0,
        total_score=10.0,
        strength="core",
        reasons=["반복 지지"],
    )

    candidates, selected = detector.choose_invalidation_zone([core_zone], snapshot)

    assert selected is not None
    assert selected.reasons
    assert "150일선" in " ".join(selected.reasons)
    assert any(candidate.zone_type == "invalidation" for candidate in candidates)


def test_choose_invalidation_zone_falls_back_to_recent_swing_low():
    snapshot = IndicatorSnapshot(price=200.0, change_pct=1.0, swing_low=185.0)
    detector = StructureZoneDetector()
    secondary_zone = StructureZone(
        zone_type="demand",
        lower_bound=188.0,
        upper_bound=194.0,
        mid_price=191.0,
        touch_count=1,
        last_touch_date="2026-01-01",
        touch_score=1.0,
        recency_score=1.0,
        volume_reaction_score=0.5,
        confluence_score=0.0,
        total_score=1.5,
        strength="secondary",
        reasons=["약한 지지"],
    )

    _, selected = detector.choose_invalidation_zone([secondary_zone], snapshot)

    assert selected is not None
    assert selected.lower_bound == 185.0
    assert "swing low" in " ".join(selected.reasons).lower()


def test_detector_marks_no_clear_structure_when_selected_zone_is_weak():
    detector = StructureZoneDetector()
    weak_zone = StructureZone(
        zone_type="demand",
        lower_bound=98.0,
        upper_bound=99.0,
        mid_price=98.5,
        touch_count=1,
        last_touch_date="2025-01-01",
        touch_score=1.0,
        recency_score=1.0,
        volume_reaction_score=0.2,
        confluence_score=0.0,
        total_score=1.0,
        strength="secondary",
    )

    no_clear, reason_codes = detector._derive_no_clear_structure(
        demand_zones=[weak_zone],
        supply_zones=[],
        balance_zones=[],
    )

    assert no_clear is True
    assert "top_score_weak" in reason_codes


def test_detector_selection_trace_is_stable_and_structured():
    detector = StructureZoneDetector()
    zone = StructureZone(
        zone_type="demand",
        lower_bound=18.0,
        upper_bound=19.0,
        mid_price=18.5,
        touch_count=3,
        last_touch_date="2026-05-01",
        touch_score=4.0,
        recency_score=4.0,
        volume_reaction_score=3.0,
        confluence_score=2.0,
        total_score=13.0,
        strength="core",
        reason_codes=["support_episode_recent"],
        reason_context={"touch_count": 3},
    )

    trace = detector._build_selection_trace(
        selected_label="support_zone",
        selected_zone=zone,
        dropped_candidates=[],
        candidate_priority_trace=[],
        no_clear_structure=False,
    )

    assert trace[0]["selected_label"] == "support_zone"
    assert trace[1]["reason_codes"] == ["support_episode_recent"]


def test_detector_selection_trace_includes_dropped_candidate_reasons():
    detector = StructureZoneDetector()
    dropped = detector._build_dropped_candidate_entry(
        zone=StructureZone(
            zone_type="supply",
            lower_bound=150.0,
            upper_bound=160.0,
            mid_price=155.0,
            touch_count=3,
            last_touch_date="2026-01-01",
            touch_score=3.0,
            recency_score=1.0,
            volume_reaction_score=1.0,
            confluence_score=0.0,
            total_score=2.0,
            strength="secondary",
        ),
        reason_code="selection_guard_failed_non_preferred",
    )
    trace = detector._build_selection_trace(
        selected_label="support_zone",
        selected_zone=None,
        dropped_candidates=[dropped],
        candidate_priority_trace=[],
        no_clear_structure=False,
    )

    assert "dropped_candidates" in trace[1]
    assert (
        trace[1]["dropped_candidates"][0]["reason_code"] == "selection_guard_failed_non_preferred"
    )


def test_detector_collects_touch_episodes_metadata():
    dates = pd.date_range("2026-01-01", periods=220, freq="D")
    price_wave = [100.0 + ((index % 20) * 0.4) for index in range(220)]
    df = pd.DataFrame(
        {
            "Open": price_wave,
            "High": [price + 2.0 for price in price_wave],
            "Low": [price - 2.0 for price in price_wave],
            "Close": price_wave,
            "Volume": [1_000_000 + index * 500 for index in range(220)],
        },
        index=dates,
    )
    snapshot = IndicatorSnapshot(price=price_wave[-1], change_pct=0.0, atr=2.0, sma_150=100.0)

    zone_set = StructureZoneDetector().detect(df, snapshot)

    assert isinstance(zone_set.touch_episodes, list)
    assert zone_set.touch_episodes
    top_episode_entry = zone_set.touch_episodes[0]
    assert "episodes" in top_episode_entry
    assert top_episode_entry["touch_episode_count"] >= 1


def test_episode_touch_score_prefers_recent_dense_episodes():
    detector = StructureZoneDetector()
    old_dense = [
        {
            "start_date": "2024-01-01",
            "end_date": "2024-01-20",
            "touch_count": 10,
            "recency_score": 1.0,
            "episode_score": 7.3,
        }
    ]
    recent_split = [
        {
            "start_date": "2026-03-01",
            "end_date": "2026-03-05",
            "touch_count": 4,
            "recency_score": 5.0,
            "episode_score": 4.3,
        },
        {
            "start_date": "2026-04-01",
            "end_date": "2026-04-07",
            "touch_count": 4,
            "recency_score": 5.0,
            "episode_score": 4.3,
        },
    ]

    old_metrics = detector._score_touch_from_episodes(old_dense, fallback_touch_count=10)
    recent_metrics = detector._score_touch_from_episodes(recent_split, fallback_touch_count=8)

    assert recent_metrics["touch_score"] > old_metrics["touch_score"]
    assert recent_metrics["guard_recency"] > old_metrics["guard_recency"]


def test_selection_guard_uses_episode_guard_recency_when_available():
    detector = StructureZoneDetector(
        StructureZoneConfig(
            selection_min_recency_score=3.0,
            selection_max_distance_pct=0.5,
        )
    )
    zone = StructureZone(
        zone_type="demand",
        lower_bound=95.0,
        upper_bound=99.0,
        mid_price=97.0,
        touch_count=5,
        last_touch_date="2026-04-20",
        touch_score=6.0,
        recency_score=5.0,
        volume_reaction_score=3.0,
        confluence_score=0.0,
        total_score=6.0,
        strength="core",
        reason_context={"episode_guard_recency": 1.0},
    )

    assert detector._passes_selection_guard(zone, current_price=100.0) is False


def test_detector_primary_label_prefers_higher_score_over_fixed_order():
    detector = StructureZoneDetector()
    demand = StructureZone(
        zone_type="demand",
        lower_bound=95.0,
        upper_bound=98.0,
        mid_price=96.5,
        touch_count=2,
        last_touch_date="2026-05-01",
        touch_score=2.0,
        recency_score=5.0,
        volume_reaction_score=2.0,
        confluence_score=0.0,
        total_score=6.0,
        strength="core",
    )
    supply = StructureZone(
        zone_type="supply",
        lower_bound=105.0,
        upper_bound=109.0,
        mid_price=107.0,
        touch_count=4,
        last_touch_date="2026-05-02",
        touch_score=4.0,
        recency_score=5.0,
        volume_reaction_score=3.0,
        confluence_score=0.0,
        total_score=9.0,
        strength="core",
    )

    label, zone, priority_trace = detector._pick_primary_selected_zone(
        demand_zones=[demand],
        supply_zones=[supply],
        balance_zones=[],
        current_price=100.0,
    )

    assert label == "resistance_zone"
    assert zone is not None
    assert zone.total_score == 9.0
    assert priority_trace
    assert any(item["label"] == "resistance_zone" for item in priority_trace)


def test_select_best_zone_uses_proximity_and_episode_recency():
    detector = StructureZoneDetector()
    far_old = StructureZone(
        zone_type="demand",
        lower_bound=60.0,
        upper_bound=70.0,
        mid_price=65.0,
        touch_count=9,
        last_touch_date="2025-01-10",
        touch_score=7.5,
        recency_score=1.0,
        volume_reaction_score=4.0,
        confluence_score=0.0,
        total_score=6.6,
        strength="core",
        reason_context={"episode_recent_score": 1.0},
    )
    near_recent = StructureZone(
        zone_type="demand",
        lower_bound=95.0,
        upper_bound=99.0,
        mid_price=97.0,
        touch_count=6,
        last_touch_date="2026-04-20",
        touch_score=6.9,
        recency_score=5.0,
        volume_reaction_score=4.0,
        confluence_score=0.0,
        total_score=6.4,
        strength="core",
        reason_context={"episode_recent_score": 5.0},
    )

    selected = detector._select_best_zone(
        [far_old, near_recent],
        current_price=100.0,
        label_hint="support_zone",
    )

    assert selected.mid_price == 97.0
