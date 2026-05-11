from src.tools.technical.models import (
    ExecutionLevelView,
    InvalidationLevelView,
    StructureLevelsPayloadV2,
    StructureLevelView,
)
from src.tools.technical.structure_presentation import StructurePresentationAdapter


def test_structure_presentation_adapter_builds_cli_and_llm_context():
    structure_levels = StructureLevelsPayloadV2(
        summary_label="support_zone",
        headline="핵심 지지 존 우위",
        why="최근 지지 터치가 집중",
        active_box=None,
        support_zones=[
            StructureLevelView(
                lower_bound=18.0,
                upper_bound=19.0,
                mid_price=18.5,
                strength="core",
                reasons=["support"],
                touch_count=4,
                last_touch_date="2026-05-01",
                total_score=10.0,
            )
        ],
        resistance_zones=[],
        former_levels=[],
        invalidation=InvalidationLevelView(
            label="18.00~19.00 하향 이탈",
            lower_bound=18.0,
            upper_bound=19.0,
            reference="support",
            reasons=["support"],
        ),
        patterns_reference=[],
    )
    execution_levels = [
        ExecutionLevelView(
            type="pivot_s1",
            description="피봇 S1",
            price=19.2,
            distance_pct=-1.3,
        )
    ]

    payload = StructurePresentationAdapter().adapt(structure_levels, execution_levels)

    assert payload.top_judgment == "현재 핵심 구조: support_zone"
    assert any("지지 존" in block for block in payload.cli_blocks)
    assert "support_zones" in payload.llm_context
    assert "피봇 S1" in payload.execution_summary
