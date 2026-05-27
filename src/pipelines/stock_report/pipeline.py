from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from langsmith import get_current_run_tree, traceable

from src.pipelines.stock_report.classify import classify_messages
from src.pipelines.stock_report.config import (
    get_report_synthesis_llm_config,
    get_semantic_extraction_llm_config,
)
from src.pipelines.stock_report.db import (
    apply_migrations,
    connect_db,
    load_telegram_messages_by_date,
    persist_classified_chunks,
    persist_report_artifact,
    resolve_db_dsn,
)
from src.pipelines.stock_report.normalize import normalize_messages, persist_normalized_messages
from src.pipelines.stock_report.render_markdown import render_stock_report_markdown
from src.pipelines.stock_report.retrieval import load_same_day_bundle
from src.pipelines.stock_report.synthesize import synthesize_same_day_bundle
from src.pipelines.stock_report.taxonomy import load_taxonomy_registry
from src.pipelines.stock_report.telegram_ingest import TelegramIngestStats, ingest_telegram_raw_csvs


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DailyV2RunResult:
    date: str
    provider: str
    compare: bool
    csv_files: int
    parsed_rows: int
    upserted_rows: int
    normalized_rows: int
    grouped_only_rows: int
    skipped_rows: int
    message_type_counts: dict[str, int]
    category_counts: dict[str, int]
    category_bucket_count: int
    theme_bucket_count: int
    focus_ticker_count: int
    low_confidence_count: int
    report_run_id: int | None
    output_markdown: str
    preview_canonical_summaries: list[str]
    migrations_applied: list[str]


def _validate_date(date: str) -> str:
    normalized = date.strip().replace("/", "-")
    datetime.strptime(normalized, "%Y-%m-%d")
    return normalized


def _load_normalize_config(config_path: str = "config.yaml") -> tuple[set[str], int, int]:
    path = Path(config_path)
    if not path.exists():
        return {"hana_us_stock"}, 100, 30

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    normalize = payload.get("stock_report", {}).get("normalize", {})
    channels = set(normalize.get("short_comment_channels", ["hana_us_stock"]))
    max_chars = int(normalize.get("short_comment_max_chars", 100))
    window = int(normalize.get("group_window_minutes", 30))
    return channels, max_chars, window


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _summarize_markdown_for_trace(markdown: str) -> dict[str, Any]:
    return {
        "type": "str",
        "chars": len(markdown),
        "sha256": _sha256_text(markdown),
    }


def _summarize_evidence_refs_for_trace(evidence_refs) -> dict[str, Any]:
    refs = list(evidence_refs or [])
    section_counts: dict[str, int] = {}
    chunk_ids: list[int] = []
    sources: list[str] = []
    for ref in refs:
        section = getattr(ref, "section_key", "unknown")
        section_counts[section] = section_counts.get(section, 0) + 1
        chunk_id = getattr(ref, "knowledge_chunk_id", None)
        if chunk_id is not None and len(chunk_ids) < 50:
            chunk_ids.append(chunk_id)
        snapshot = getattr(ref, "knowledge_chunk_snapshot", {}) or {}
        channel = snapshot.get("channel_name") or snapshot.get("channel_key")
        message_id = snapshot.get("channel_message_id")
        if channel and message_id and len(sources) < 50:
            source = f"{channel}#{message_id}"
            if source not in sources:
                sources.append(source)
    return {
        "type": "evidence_refs",
        "count": len(refs),
        "section_counts": section_counts,
        "sample_chunk_ids": chunk_ids,
        "sample_sources": sources,
    }


def _summarize_report_artifact_for_trace(report_artifact) -> dict[str, Any]:
    report_date = getattr(report_artifact, "report_date", None)
    if hasattr(report_date, "isoformat"):
        report_date = report_date.isoformat()
    return {
        "type": "StockReportArtifact",
        "report_date": report_date,
        "pulse_count": len(getattr(report_artifact, "pulse", []) or []),
        "category_summary_count": len(getattr(report_artifact, "category_summaries", []) or []),
        "core_theme_count": len(getattr(report_artifact, "core_themes", []) or []),
        "focus_ticker_count": len(getattr(report_artifact, "focus_tickers", []) or []),
        "low_confidence_count": len(getattr(report_artifact, "low_confidence_notes", []) or []),
        "evidence_ref_count": len(getattr(report_artifact, "evidence_refs", []) or []),
    }


def _trace_final_report_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in inputs.items():
        if key == "conn":
            sanitized[key] = "<redacted:connection>"
        elif key == "report_artifact":
            sanitized[key] = _summarize_report_artifact_for_trace(value)
        elif key == "output_markdown" and isinstance(value, str):
            sanitized[key] = _summarize_markdown_for_trace(value)
        elif key == "evidence_refs":
            sanitized[key] = _summarize_evidence_refs_for_trace(value)
        elif hasattr(value, "isoformat"):
            sanitized[key] = value.isoformat()
        else:
            sanitized[key] = value
    return sanitized


def _trace_final_report_outputs(output: Any) -> Any:
    if isinstance(output, str):
        return _summarize_markdown_for_trace(output)
    return output


@traceable(name="Stock Report Daily V2 - Ingest")
def _stage_ingest(conn, date: str, data_dir: str) -> TelegramIngestStats:
    return ingest_telegram_raw_csvs(conn=conn, date=date, data_dir=data_dir)


@traceable(name="Stock Report Daily V2 - Normalize")
def _stage_normalize(raw_messages, *, short_channels: set[str], max_chars: int, group_window: int):
    return normalize_messages(
        raw_messages,
        short_comment_channels=short_channels,
        short_comment_max_chars=max_chars,
        group_window_minutes=group_window,
    )


@traceable(name="Stock Report Daily V2 - Classify")
def _stage_classify(normalized, *, taxonomy, provider: str):
    return classify_messages(normalized, taxonomy=taxonomy, provider=provider)


@traceable(name="Stock Report Daily V2 - Persist Chunks")
def _stage_persist_chunks(conn, *, normalized_messages, classified_messages) -> None:
    persist_classified_chunks(
        conn,
        normalized_messages=normalized_messages,
        classified_messages=classified_messages,
    )


@traceable(name="Stock Report Daily V2 - Load Same Day Bundle")
def _stage_load_same_day_bundle(conn, date: str):
    return load_same_day_bundle(conn, date)


@traceable(name="Stock Report Daily V2 - Local Evidence Synthesis")
def _stage_local_evidence_synthesis(bundle, *, provider: str):
    return synthesize_same_day_bundle(bundle, provider=provider)


@traceable(
    name="Stock Report Daily V2 - Render Markdown",
    process_inputs=_trace_final_report_inputs,
    process_outputs=_trace_final_report_outputs,
)
def _stage_render_markdown(report_artifact):
    return render_stock_report_markdown(report_artifact)


@traceable(
    name="Stock Report Daily V2 - Persist Report",
    process_inputs=_trace_final_report_inputs,
)
def _stage_persist_report(conn, *, report_date, provider: str, output_markdown: str, evidence_refs):
    return persist_report_artifact(
        conn,
        report_date=report_date,
        provider=provider,
        output_markdown=output_markdown,
        evidence_refs=evidence_refs,
    )


@traceable(name="Stock Report Daily V2 - Load Messages")
def _stage_load_raw_messages(conn, date: str):
    return load_telegram_messages_by_date(conn, date)


@traceable(name="Stock Report Daily V2 - Persist Normalized")
def _stage_persist_normalized(conn, normalized) -> None:
    persist_normalized_messages(conn, normalized)


@traceable(name="Stock Report Daily V2")
def run_daily_v2(
    date: str,
    data_dir: str = "data",
    provider: str = "openai",
    compare: bool = False,
    dsn: str | None = None,
    migrations_dir: str = "migrations/stock_report",
    config_path: str = "config.yaml",
    taxonomy_path: str = "config/stock_report_vocabulary.yaml",
    preview_limit: int = 12,
) -> DailyV2RunResult:
    date = _validate_date(date)
    run_tree = get_current_run_tree()
    if run_tree:
        run_tree.name = f"Stock Report Daily V2 - {date}"
    resolved_dsn = resolve_db_dsn(dsn)
    migrations_path = Path(migrations_dir)
    short_channels, max_chars, group_window = _load_normalize_config(config_path)
    taxonomy = load_taxonomy_registry(taxonomy_path)
    semantic_llm_config = get_semantic_extraction_llm_config(provider)
    synthesis_llm_config = get_report_synthesis_llm_config(provider)
    logger.info(
        "daily-v2 started: date=%s provider=%s semantic_model=%s synthesis_model=%s data_dir=%s",
        date,
        provider,
        semantic_llm_config.model,
        synthesis_llm_config.model,
        data_dir,
    )

    with connect_db(resolved_dsn) as conn:
        migrations_applied = apply_migrations(conn, migrations_path)
        logger.info("daily-v2 migrations applied: %s", migrations_applied or ["none"])
        ingest_stats: TelegramIngestStats = _stage_ingest(conn, date, data_dir)
        logger.info(
            "daily-v2 ingest completed: csv_files=%d parsed_rows=%d upserted_rows=%d",
            ingest_stats.csv_files,
            ingest_stats.parsed_rows,
            ingest_stats.upserted_rows,
        )
        raw_messages = _stage_load_raw_messages(conn, date)
        logger.info("daily-v2 loaded raw messages: count=%d", len(raw_messages))
        normalized = _stage_normalize(
            raw_messages,
            short_channels=short_channels,
            max_chars=max_chars,
            group_window=group_window,
        )
        logger.info("daily-v2 normalization completed: normalized_rows=%d", len(normalized))
        _stage_persist_normalized(conn, normalized)
        logger.info("daily-v2 normalized messages persisted")
        classified = _stage_classify(normalized, taxonomy=taxonomy, provider=provider)
        logger.info("daily-v2 classification completed: classified_units=%d", len(classified))
        _stage_persist_chunks(
            conn,
            normalized_messages=normalized,
            classified_messages=classified,
        )
        logger.info("daily-v2 classified chunks persisted")
        same_day_bundle = _stage_load_same_day_bundle(conn, date)
        report_artifact = _stage_local_evidence_synthesis(same_day_bundle, provider=provider)
        output_markdown = _stage_render_markdown(report_artifact)
        report_run_id = _stage_persist_report(
            conn,
            report_date=report_artifact.report_date,
            provider=provider,
            output_markdown=output_markdown,
            evidence_refs=report_artifact.evidence_refs,
        )
        logger.info(
            "daily-v2 report artifact persisted: report_run_id=%s categories=%d themes=%d focus_tickers=%d low_confidence=%d",
            report_run_id,
            len(same_day_bundle.category_buckets),
            sum(len(bucket.theme_buckets) for bucket in same_day_bundle.category_buckets),
            len(same_day_bundle.focus_ticker_buckets),
            len(same_day_bundle.low_confidence_chunks),
        )

    grouped_only_rows = sum(1 for row in normalized if row.processing_mode == "grouped_only")
    skipped_rows = sum(1 for row in normalized if row.processing_mode == "skip")
    message_type_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    preview_canonical_summaries: list[str] = []
    for row in classified:
        message_type_counts[row.message_type] = message_type_counts.get(row.message_type, 0) + 1
        effective_category = row.category_key
        if effective_category == "unclassified" and row.provisional_category:
            effective_category = row.provisional_category
        category_counts[effective_category] = category_counts.get(effective_category, 0) + 1
        if row.canonical_summary != "-" and len(preview_canonical_summaries) < preview_limit:
            preview_type = row.message_type
            if row.event_type:
                preview_type = f"{preview_type}/{row.event_type}"
            preview_category = row.category_key
            if preview_category == "unclassified" and row.provisional_category:
                preview_category = row.provisional_category
            preview_canonical_summaries.append(
                f"[{preview_type}] ({preview_category}) {row.canonical_summary}"
            )
    logger.info(
        "daily-v2 summary: normalized_rows=%d grouped_only_rows=%d skipped_rows=%d classified_units=%d",
        len(normalized),
        grouped_only_rows,
        skipped_rows,
        len(classified),
    )

    return DailyV2RunResult(
        date=date,
        provider=provider,
        compare=compare,
        csv_files=ingest_stats.csv_files,
        parsed_rows=ingest_stats.parsed_rows,
        upserted_rows=ingest_stats.upserted_rows,
        normalized_rows=len(normalized),
        grouped_only_rows=grouped_only_rows,
        skipped_rows=skipped_rows,
        message_type_counts=message_type_counts,
        category_counts=category_counts,
        category_bucket_count=len(same_day_bundle.category_buckets),
        theme_bucket_count=sum(
            len(bucket.theme_buckets) for bucket in same_day_bundle.category_buckets
        ),
        focus_ticker_count=len(same_day_bundle.focus_ticker_buckets),
        low_confidence_count=len(same_day_bundle.low_confidence_chunks),
        report_run_id=report_run_id,
        output_markdown=output_markdown,
        preview_canonical_summaries=preview_canonical_summaries,
        migrations_applied=migrations_applied,
    )


def run_validate_v2(
    date: str,
    data_dir: str = "data",
    provider: str = "openai",
    dsn: str | None = None,
    migrations_dir: str = "migrations/stock_report",
    config_path: str = "config.yaml",
    taxonomy_path: str = "config/stock_report_vocabulary.yaml",
    preview_limit: int = 12,
) -> DailyV2RunResult:
    return run_daily_v2(
        date=date,
        data_dir=data_dir,
        provider=provider,
        compare=True,
        dsn=dsn,
        migrations_dir=migrations_dir,
        config_path=config_path,
        taxonomy_path=taxonomy_path,
        preview_limit=preview_limit,
    )


def format_daily_v2_report(result: DailyV2RunResult) -> str:
    if result.output_markdown:
        return result.output_markdown

    lines = [
        "# Daily Report V2 (Scaffold)",
        "",
        f"- date: `{result.date}`",
        f"- provider: `{result.provider}`",
        f"- compare mode: `{result.compare}`",
        f"- csv files: `{result.csv_files}`",
        f"- parsed rows: `{result.parsed_rows}`",
        f"- upserted rows: `{result.upserted_rows}`",
        f"- normalized rows: `{result.normalized_rows}`",
        f"- grouped_only rows: `{result.grouped_only_rows}`",
        f"- skipped rows: `{result.skipped_rows}`",
        f"- message_type counts: `{result.message_type_counts}`",
        f"- category counts: `{result.category_counts}`",
        f"- category buckets: `{result.category_bucket_count}`",
        f"- theme buckets: `{result.theme_bucket_count}`",
        f"- focus ticker buckets: `{result.focus_ticker_count}`",
        f"- low confidence chunks: `{result.low_confidence_count}`",
    ]

    if result.migrations_applied:
        lines.append(f"- applied migrations: `{', '.join(result.migrations_applied)}`")
    else:
        lines.append("- applied migrations: `none`")

    if result.preview_canonical_summaries:
        lines.append("")
        lines.append("## Preview canonical_summary")
        lines.extend(f"- {item}" for item in result.preview_canonical_summaries)

    return "\n".join(lines)
