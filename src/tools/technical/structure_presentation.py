from src.tools.technical.models import (
    ExecutionLevelView,
    StructureLevelsPayloadV2,
    StructurePresentationPayload,
)


def _format_zone_range(lower_bound: float, upper_bound: float) -> str:
    return f"{lower_bound:.2f}~{upper_bound:.2f}"


def _format_zone_list(items: list) -> str:
    if not items:
        return "없음"
    return ", ".join(_format_zone_range(item.lower_bound, item.upper_bound) for item in items)


def _format_execution_list(items: list[ExecutionLevelView]) -> str:
    if not items:
        return "없음"
    return ", ".join(
        f"{item.description} ${item.price:.2f} ({item.distance_pct:+.1f}%)" for item in items
    )


class StructurePresentationAdapter:
    """Translate translated structure payload into CLI/LLM presentation views."""

    def adapt(
        self,
        structure_levels: StructureLevelsPayloadV2,
        execution_levels: list[ExecutionLevelView],
    ) -> StructurePresentationPayload:
        top_judgment = f"현재 핵심 구조: {structure_levels.summary_label}"

        invalidation = (
            structure_levels.invalidation.label if structure_levels.invalidation else "없음"
        )
        support_text = _format_zone_list(structure_levels.support_zones)
        resistance_text = _format_zone_list(structure_levels.resistance_zones)
        former_text = _format_zone_list(structure_levels.former_levels)
        active_box_text = (
            _format_zone_range(
                structure_levels.active_box.lower_bound,
                structure_levels.active_box.upper_bound,
            )
            if structure_levels.active_box
            else "없음"
        )
        execution_text = _format_execution_list(execution_levels)

        cli_blocks = [
            "## 구조 레벨",
            f"- **요약**: {structure_levels.headline}",
            f"- **근거**: {structure_levels.why}",
            f"- **박스 존**: {active_box_text}",
            f"- **지지 존**: {support_text}",
            f"- **저항 존**: {resistance_text}",
            f"- **전환 레벨**: {former_text}",
            f"- **무효화 기준**: {invalidation}",
            "",
            "## 실행 레벨",
            f"- **핵심 실행 레벨**: {execution_text}",
            "",
        ]

        llm_context = "\n".join(
            [
                "구조 레벨:",
                f"- summary_label: {structure_levels.summary_label}",
                f"- headline: {structure_levels.headline}",
                f"- why: {structure_levels.why}",
                f"- active_box: {active_box_text}",
                f"- support_zones: {support_text}",
                f"- resistance_zones: {resistance_text}",
                f"- former_levels: {former_text}",
                f"- invalidation: {invalidation}",
                "",
                "실행 레벨:",
                f"- {execution_text}",
            ]
        )

        return StructurePresentationPayload(
            top_judgment=top_judgment,
            headline=structure_levels.headline,
            why=structure_levels.why,
            cli_blocks=cli_blocks,
            llm_context=llm_context,
            structure_summary=(
                f"{structure_levels.headline} | 지지 {len(structure_levels.support_zones)}개, "
                f"저항 {len(structure_levels.resistance_zones)}개"
            ),
            execution_summary=execution_text,
        )


def build_structure_presentation(
    structure_levels: StructureLevelsPayloadV2,
    execution_levels: list[ExecutionLevelView],
) -> StructurePresentationPayload:
    return StructurePresentationAdapter().adapt(structure_levels, execution_levels)
