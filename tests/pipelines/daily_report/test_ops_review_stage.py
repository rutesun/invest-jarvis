from src.pipelines.daily_report.stages.ops_review_stage import build_ops_knowledge_report
from src.pipelines.daily_report.telemetry import StageTelemetry


def test_ops_review_promotes_unknown_entity_to_candidate():
    telemetry = StageTelemetry(
        unknown_entities=["HBM4 base die"],
        low_confidence_edges=[],
        counters={"candidate_count": 1},
    )

    report = build_ops_knowledge_report(telemetry, date="2026-04-29")

    assert report.candidates[0].candidate_type == "concept"
    assert "HBM4 base die" in report.markdown
