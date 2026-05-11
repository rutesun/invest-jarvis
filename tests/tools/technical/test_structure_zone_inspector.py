import pandas as pd

from src.tools.technical.models import (
    ExecutionLevelView,
    IndicatorSnapshot,
    InvalidationLevelView,
    LevelPayload,
    StructureLevelsPayloadV2,
    StructureLevelView,
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
)
from src.tools.technical.structure_presentation import build_structure_presentation
from src.tools.technical.structure_zone_inspector import (
    build_indicator_snapshot_from_ohlcv,
    build_structure_zone_inspect_payload,
    compare_structure_zone_inspect_payloads,
    format_structure_zone_inspect_comparison,
    format_structure_zone_inspection,
)


def _sample_zone_set() -> StructureZoneSet:
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
        reasons=["반복 지지", "거래량 반응 3.00"],
        reason_context={
            "confluence_sources": ["MA150", "POC", "HVNx1"],
            "confluence_components": {
                "ma_overlaps": {
                    "sma_150": {"value": 202.0, "overlap": True},
                    "sma_200": {"value": 180.0, "overlap": False},
                },
                "poc_overlap": True,
                "poc_range": {"lower": 201.0, "upper": 204.0},
                "hvn_overlap_count": 1,
            },
        },
    )
    supply = StructureZone(
        zone_type="supply",
        lower_bound=218.0,
        upper_bound=223.0,
        mid_price=220.5,
        touch_count=3,
        last_touch_date="2026-05-03",
        touch_score=3.0,
        recency_score=5.0,
        volume_reaction_score=2.0,
        confluence_score=1.0,
        total_score=11.0,
        strength="core",
        reasons=["반복 저항", "거래량 반응 2.00"],
        reason_context={
            "confluence_sources": ["MA200"],
            "confluence_components": {
                "ma_overlaps": {
                    "sma_150": {"value": 202.0, "overlap": False},
                    "sma_200": {"value": 220.5, "overlap": True},
                },
                "poc_overlap": False,
                "poc_range": None,
                "hvn_overlap_count": 0,
            },
        },
    )
    invalidation = StructureZone(
        zone_type="invalidation",
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
        reasons=["반복 지지", "150일선 fallback"],
    )
    return StructureZoneSet(
        demand_zones=[demand],
        supply_zones=[supply],
        selection_trace=[
            {"selected_label": "support_zone", "no_clear_structure": False},
            {
                "selection_priority_trace": [
                    {
                        "label": "support_zone",
                        "zone_type": "demand",
                        "lower_bound": 200.0,
                        "upper_bound": 205.0,
                        "total_score": 13.0,
                        "priority_score": 13.4,
                        "distance_pct": 0.0357,
                        "episode_recent_score": 4.5,
                    }
                ]
            },
        ],
        invalidation_candidates=[invalidation],
        invalidation_zone=invalidation,
        all_candidates=[demand, supply, invalidation],
        touch_episodes=[
            {
                "zone_type": "demand",
                "lower_bound": 200.0,
                "upper_bound": 205.0,
                "total_score": 13.0,
                "touch_episode_count": 1,
                "episodes": [
                    {
                        "start_date": "2026-04-21",
                        "end_date": "2026-05-01",
                        "touch_count": 4,
                        "recency_score": 5.0,
                        "episode_score": 4.3,
                        "touch_dates": ["2026-04-21", "2026-04-25", "2026-04-29", "2026-05-01"],
                    }
                ],
            }
        ],
    )


def _sample_level_payload() -> LevelPayload:
    structure_levels = StructureLevelsPayloadV2(
        summary_label="support_zone",
        headline="핵심 지지 존 우위",
        why="최근 지지 반응 우세",
        active_box=None,
        support_zones=[
            StructureLevelView(
                lower_bound=200.0,
                upper_bound=205.0,
                mid_price=202.5,
                strength="core",
                reasons=["반복 지지"],
                touch_count=4,
                last_touch_date="2026-05-01",
                total_score=13.0,
            )
        ],
        resistance_zones=[
            StructureLevelView(
                lower_bound=218.0,
                upper_bound=223.0,
                mid_price=220.5,
                strength="core",
                reasons=["반복 저항"],
                touch_count=3,
                last_touch_date="2026-05-03",
                total_score=11.0,
            )
        ],
        former_levels=[
            StructureLevelView(
                lower_bound=208.0,
                upper_bound=212.0,
                mid_price=210.0,
                strength="core",
                reasons=["수요/공급 중첩"],
                touch_count=5,
                last_touch_date="2026-05-02",
                total_score=11.5,
            )
        ],
        invalidation=InvalidationLevelView(
            label="200.00~205.00 + 150일선 하향 이탈",
            lower_bound=200.0,
            upper_bound=205.0,
            reference="반복 지지",
            reasons=["반복 지지", "150일선 fallback"],
        ),
        patterns_reference=[],
    )
    execution_levels = [
        ExecutionLevelView(
            type="pivot_s1",
            description="피봇 S1",
            price=206.0,
            distance_pct=-2.0,
        ),
        ExecutionLevelView(
            type="sma_50",
            description="50일선",
            price=201.0,
            distance_pct=-4.4,
        ),
    ]
    return LevelPayload(
        structure_levels=structure_levels,
        execution_levels=execution_levels,
        structure_summary="핵심 지지 존 우위 | 지지 1개, 저항 1개, 전환 1개",
        execution_summary="피봇 S1 $206.00 (-2.0%), 50일선 $201.00 (-4.4%)",
    )


def test_build_structure_zone_inspect_payload_includes_selected_and_score_breakdown():
    snapshot = IndicatorSnapshot(
        price=210.0,
        change_pct=1.5,
        atr=4.0,
        sma_50=201.0,
        sma_150=188.0,
    )

    payload = build_structure_zone_inspect_payload(
        symbol="ALAB",
        snapshot=snapshot,
        zone_set=_sample_zone_set(),
        level_payload=_sample_level_payload(),
        presented_structure=build_structure_presentation(
            _sample_level_payload().structure_levels,
            _sample_level_payload().execution_levels,
        ),
        csv_path="tests/fixtures/technical/structure_zones/ALAB.csv",
        config=StructureZoneConfig(top_n_per_side=5),
        source="fixture",
    )

    assert payload["symbol"] == "ALAB"
    assert payload["source"] == "fixture"
    assert payload["structure_summary"]
    assert payload["execution_summary"]
    assert payload["structure_levels"]["support_zones"][0]["lower_bound"] == 200.0
    assert payload["execution_levels"][0]["type"] == "pivot_s1"
    assert payload["artifact"]["params"]["top_n_per_side"] == 5
    assert len(payload["artifact"]["candidates"]) == 3
    assert payload["artifact"]["score_breakdown"][0]["total_score"] == 13.0
    assert payload["touch_episodes"][0]["touch_episode_count"] == 1


def test_build_indicator_snapshot_from_ohlcv_populates_minimum_levels():
    df = pd.DataFrame(
        {
            "Open": [100.0, 102.0, 101.0, 103.0],
            "High": [103.0, 104.0, 105.0, 106.0],
            "Low": [99.0, 100.0, 99.5, 101.0],
            "Close": [102.0, 101.0, 103.0, 104.0],
            "Volume": [1_000_000, 1_100_000, 900_000, 1_200_000],
        },
        index=pd.date_range("2026-01-01", periods=4, freq="D"),
    )

    snapshot = build_indicator_snapshot_from_ohlcv(df)

    assert snapshot.price == 104.0
    assert snapshot.atr is not None
    assert snapshot.sma_50 is not None
    assert snapshot.sma_150 is not None
    assert snapshot.pivot is not None
    assert snapshot.support_s1 is not None
    assert snapshot.resistance_r1 is not None


def test_format_structure_zone_inspection_shows_selected_and_candidate_sections():
    snapshot = IndicatorSnapshot(
        price=210.0,
        change_pct=1.5,
        atr=4.0,
        sma_50=201.0,
        sma_150=188.0,
    )
    payload = build_structure_zone_inspect_payload(
        symbol="ALAB",
        snapshot=snapshot,
        zone_set=_sample_zone_set(),
        level_payload=_sample_level_payload(),
        presented_structure=build_structure_presentation(
            _sample_level_payload().structure_levels,
            _sample_level_payload().execution_levels,
        ),
        csv_path="tests/fixtures/technical/structure_zones/ALAB.csv",
        config=StructureZoneConfig(),
        source="fixture",
    )

    output = format_structure_zone_inspection(payload, max_candidates=2)

    assert "# Structure Zone Inspect: ALAB" in output
    assert "## 입력 요약" in output
    assert "## 선택된 구조 레벨" in output
    assert "## 실행 레벨" in output
    assert "## 후보 점수" in output
    assert "## 선택 우선순위 점수" in output
    assert "## 터치 에피소드" in output
    assert "200.00~205.00" in output
    assert "지지 존" in output
    assert "피봇 S1" in output
    assert "touch=4.00" in output
    assert "volume=3.00" in output
    assert "confluence 근거: MA150(202.00), POC(201.00~204.00), HVNx1" in output


def test_compare_structure_zone_inspect_payloads_builds_score_diff():
    baseline_payload = build_structure_zone_inspect_payload(
        symbol="ALAB",
        snapshot=IndicatorSnapshot(price=210.0, change_pct=1.5, atr=4.0),
        zone_set=_sample_zone_set(),
        level_payload=_sample_level_payload(),
        presented_structure=build_structure_presentation(
            _sample_level_payload().structure_levels,
            _sample_level_payload().execution_levels,
        ),
        config=StructureZoneConfig(),
        source="fixture",
    )

    changed_zone_set = _sample_zone_set()
    changed_zone_set.demand_zones[0].touch_score = 2.0
    changed_zone_set.demand_zones[0].volume_reaction_score = 4.0
    changed_zone_set.demand_zones[0].total_score = 9.0
    changed_zone_set.all_candidates[0].touch_score = 2.0
    changed_zone_set.all_candidates[0].volume_reaction_score = 4.0
    changed_zone_set.all_candidates[0].total_score = 9.0

    changed_level_payload = _sample_level_payload()
    changed_level_payload.structure_levels.support_zones[0].total_score = 9.0

    current_payload = build_structure_zone_inspect_payload(
        symbol="ALAB",
        snapshot=IndicatorSnapshot(price=210.0, change_pct=1.5, atr=4.0),
        zone_set=changed_zone_set,
        level_payload=changed_level_payload,
        presented_structure=build_structure_presentation(
            changed_level_payload.structure_levels,
            changed_level_payload.execution_levels,
        ),
        config=StructureZoneConfig(),
        source="fixture",
    )

    diff = compare_structure_zone_inspect_payloads(baseline_payload, current_payload)

    assert diff["symbol"] == "ALAB"
    assert diff["selection_changes"]["support_zones"][0]["changed"] is False
    assert diff["score_changes"][0]["zone_type"] == "demand"
    assert diff["score_changes"][0]["total_delta"] == -4.0
    assert diff["score_changes"][0]["touch_delta"] == -2.0
    assert diff["score_changes"][0]["volume_delta"] == 1.0


def test_format_structure_zone_inspect_comparison_shows_selection_and_score_delta():
    baseline_payload = build_structure_zone_inspect_payload(
        symbol="ALAB",
        snapshot=IndicatorSnapshot(price=210.0, change_pct=1.5, atr=4.0),
        zone_set=_sample_zone_set(),
        level_payload=_sample_level_payload(),
        presented_structure=build_structure_presentation(
            _sample_level_payload().structure_levels,
            _sample_level_payload().execution_levels,
        ),
        config=StructureZoneConfig(),
        source="fixture",
    )

    changed_zone_set = _sample_zone_set()
    changed_zone_set.supply_zones[0].lower_bound = 224.0
    changed_zone_set.supply_zones[0].upper_bound = 229.0
    changed_zone_set.supply_zones[0].total_score = 8.0
    changed_zone_set.all_candidates[1].lower_bound = 224.0
    changed_zone_set.all_candidates[1].upper_bound = 229.0
    changed_zone_set.all_candidates[1].total_score = 8.0
    changed_level_payload = _sample_level_payload()
    changed_level_payload.structure_levels.resistance_zones[0].lower_bound = 224.0
    changed_level_payload.structure_levels.resistance_zones[0].upper_bound = 229.0
    changed_level_payload.structure_levels.resistance_zones[0].total_score = 8.0

    current_payload = build_structure_zone_inspect_payload(
        symbol="ALAB",
        snapshot=IndicatorSnapshot(price=210.0, change_pct=1.5, atr=4.0),
        zone_set=changed_zone_set,
        level_payload=changed_level_payload,
        presented_structure=build_structure_presentation(
            changed_level_payload.structure_levels,
            changed_level_payload.execution_levels,
        ),
        config=StructureZoneConfig(),
        source="fixture",
    )

    diff = compare_structure_zone_inspect_payloads(baseline_payload, current_payload)
    output = format_structure_zone_inspect_comparison(diff, max_score_changes=3)

    assert "# Structure Zone Compare: ALAB" in output
    assert "## 선택 레벨 변경" in output
    assert "## 점수 변화" in output
    assert "changed" in output
    assert "removed" in output
    assert "added" in output
