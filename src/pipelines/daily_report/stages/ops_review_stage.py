"""Ops review stage: convert telemetry into knowledge governance output."""

from src.pipelines.daily_report.models import KnowledgeCandidate, OpsKnowledgeReport
from src.pipelines.daily_report.telemetry import StageTelemetry


def build_ops_knowledge_report(telemetry: StageTelemetry, date: str) -> OpsKnowledgeReport:
    candidates = [
        KnowledgeCandidate(
            candidate_type="concept",
            key=entity,
            reason="unknown_entity_repeated",
            evidence_source_ids=[],
            priority=2,
            confidence=0.6,
        )
        for entity in telemetry.unknown_entities
    ]
    markdown = "\n".join(
        [
            "# Ops Knowledge Report",
            f"## Date: {date}",
            *[f"- candidate: {candidate.key}" for candidate in candidates],
        ]
    )
    return OpsKnowledgeReport(date=date, candidates=candidates, markdown=markdown)
