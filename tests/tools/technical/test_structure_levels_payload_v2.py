from src.tools.technical.models import (
    InvalidationLevelView,
    StructureLevelsPayloadV2,
    StructurePresentationPayload,
)


def test_structure_levels_payload_v2_has_summary_fields():
    payload = StructureLevelsPayloadV2(
        summary_label="support_zone",
        headline="최근 지지 존이 우세",
        why="최근 반등 episode가 가장 강함",
        active_box=None,
        support_zones=[],
        resistance_zones=[],
        former_levels=[],
        invalidation=InvalidationLevelView(
            label="18.00~19.00 하향 이탈",
            lower_bound=18.0,
            upper_bound=19.0,
            reference="support_zone",
            reasons=["support_episode"],
        ),
        patterns_reference=[],
    )

    assert payload.summary_label == "support_zone"
    assert payload.headline
    assert payload.why


def test_structure_presentation_payload_keeps_cli_and_llm_views_separate():
    payload = StructurePresentationPayload(
        top_judgment="현재 가장 중요한 구조: support_zone",
        headline="최근 지지 존이 우세",
        why="최근 반등 episode가 가장 강함",
        cli_blocks=["## 구조 레벨", "- **핵심 지지 존**: 18.00~19.00"],
        llm_context="구조 레벨: support_zone 18.00~19.00",
    )

    assert payload.cli_blocks[0] == "## 구조 레벨"
    assert "support_zone" in payload.llm_context
