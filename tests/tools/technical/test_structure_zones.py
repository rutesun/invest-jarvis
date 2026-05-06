from src.tools.technical.models import (
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
    ZoneTestArtifact,
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
