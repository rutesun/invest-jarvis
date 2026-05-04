"""Daily report runtime pipeline orchestration."""

import logging
from pathlib import Path

from langsmith import get_current_run_tree, traceable

from src.pipelines.daily_report.artifacts import StageArtifactStore
from src.pipelines.daily_report.config import APPROVED_KNOWLEDGE_DIR, ARTIFACTS_ROOT
from src.pipelines.daily_report.knowledge import load_approved_knowledge
from src.pipelines.daily_report.models import (
    DailyReport,
    DailyReportRun,
    OpsKnowledgeReport,
    ResearchDump,
)
from src.pipelines.daily_report.renderers import (
    render_main_report,
)
from src.pipelines.daily_report.stages.extract_stage import extract_stage
from src.pipelines.daily_report.stages.ingest_stage import ingest
from src.pipelines.daily_report.stages.link_stage import link_stage
from src.pipelines.daily_report.stages.ops_review_stage import build_ops_knowledge_report
from src.pipelines.daily_report.stages.select_stage import select_stage
from src.pipelines.daily_report.telemetry import StageTelemetry


logger = logging.getLogger(__name__)


def _build_research_dump(
    date: str, selected_clusters: list, cluster_titles: dict[str, str]
) -> ResearchDump:
    lines = ["# Research Dump", f"## Date: {date}", ""]
    for item in selected_clusters:
        title = cluster_titles.get(item.cluster_id, item.cluster_id)
        reason = ", ".join(item.reasons) if item.reasons else "n/a"
        lines.append(f"- {title}: score={item.score:.2f} | reasons={reason}")
    return ResearchDump(date=date, markdown="\n".join(lines))


def _build_main_report(
    date: str, macro, selected_clusters: list, cluster_titles: dict[str, str]
) -> DailyReport:
    insights = [
        cluster_titles.get(item.cluster_id, item.cluster_id)
        for item in selected_clusters
        if item.selected_for_brief
    ][:5]
    if not insights:
        insights = ["핵심 테마가 부족하여 원문 점검이 필요합니다"]
    return DailyReport(date=date, macro=macro, key_insights=insights, news=[])


@traceable(name="Daily Report Pipeline")
def run_pipeline(date: str, data_dir: str = "data") -> DailyReportRun:
    run_tree = get_current_run_tree()
    if run_tree:
        run_tree.name = f"Daily Report Runtime - {date}"

    artifact_store = StageArtifactStore(ARTIFACTS_ROOT / date / "run-1")
    telemetry = StageTelemetry()

    logger.info("[1/5] Ingest Stage")
    ingest_result = ingest(date, data_dir)
    artifact_store.write_json("ingest", ingest_result.model_dump(mode="json"))

    logger.info("[2/5] Extract Stage")
    extract_result = extract_stage(ingest_result.messages, date)
    artifact_store.write_json("extract", extract_result.model_dump(mode="json"))

    logger.info("[3/5] Link Stage")
    knowledge = load_approved_knowledge(APPROVED_KNOWLEDGE_DIR)
    link_result = link_stage(extract_result.claims, knowledge, date, telemetry=telemetry)
    artifact_store.write_json("link", link_result.model_dump(mode="json"))

    logger.info("[4/5] Select Stage")
    select_result = select_stage(link_result.clusters, ingest_result.macro, date)
    artifact_store.write_json("select", select_result.model_dump(mode="json"))

    cluster_titles = {cluster.cluster_id: cluster.title for cluster in link_result.clusters}
    main_report = _build_main_report(
        date=date,
        macro=ingest_result.macro,
        selected_clusters=select_result.selected_clusters,
        cluster_titles=cluster_titles,
    )
    research_dump = _build_research_dump(
        date=date,
        selected_clusters=select_result.selected_clusters,
        cluster_titles=cluster_titles,
    )
    ops_report: OpsKnowledgeReport = build_ops_knowledge_report(telemetry, date)

    artifact_store.write_markdown("main_report", render_main_report(main_report, data_dir=data_dir))
    artifact_store.write_markdown("research_dump", research_dump.markdown)
    artifact_store.write_markdown("ops_report", ops_report.markdown)

    return DailyReportRun(
        date=date,
        main_report=main_report,
        research_dump=research_dump,
        ops_report=ops_report,
        artifacts_dir=str(artifact_store.base_dir),
    )


def format_report(report: DailyReport, data_dir: str = "data") -> str:
    """Backward compatible wrapper for legacy callers."""
    return render_main_report(report, data_dir=data_dir)


if __name__ == "__main__":
    runtime = run_pipeline("2026-04-14")
    print(render_main_report(runtime.main_report))
    print(f"\nArtifacts: {Path(runtime.artifacts_dir)}")
