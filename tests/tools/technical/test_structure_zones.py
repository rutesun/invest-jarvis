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


def test_calculate_zone_half_width_respects_pct_floor_and_ceiling():
    width = calculate_zone_half_width(price=100.0, atr=1.0, config=StructureZoneConfig())

    assert width >= 1.0
    assert width <= 5.0


def test_cluster_price_candidates_groups_nearby_swings():
    clusters = cluster_price_candidates([100.0, 101.0, 118.0], half_width=2.0)

    assert clusters == [[100.0, 101.0], [118.0]]


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
