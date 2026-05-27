from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from src.pipelines.stock_report.classify import classify_messages
from src.pipelines.stock_report.config import get_semantic_extraction_llm_config
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
    datetime.strptime(date, "%Y-%m-%d")
    return date


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
    _validate_date(date)
    resolved_dsn = resolve_db_dsn(dsn)
    migrations_path = Path(migrations_dir)
    short_channels, max_chars, group_window = _load_normalize_config(config_path)
    taxonomy = load_taxonomy_registry(taxonomy_path)
    llm_config = get_semantic_extraction_llm_config(provider)
    logger.info(
        "daily-v2 started: date=%s provider=%s model=%s data_dir=%s",
        date,
        provider,
        llm_config.model,
        data_dir,
    )

    with connect_db(resolved_dsn) as conn:
        migrations_applied = apply_migrations(conn, migrations_path)
        logger.info("daily-v2 migrations applied: %s", migrations_applied or ["none"])
        ingest_stats: TelegramIngestStats = ingest_telegram_raw_csvs(
            conn=conn,
            date=date,
            data_dir=data_dir,
        )
        logger.info(
            "daily-v2 ingest completed: csv_files=%d parsed_rows=%d upserted_rows=%d",
            ingest_stats.csv_files,
            ingest_stats.parsed_rows,
            ingest_stats.upserted_rows,
        )
        raw_messages = load_telegram_messages_by_date(conn, date)
        logger.info("daily-v2 loaded raw messages: count=%d", len(raw_messages))
        normalized = normalize_messages(
            raw_messages,
            short_comment_channels=short_channels,
            short_comment_max_chars=max_chars,
            group_window_minutes=group_window,
        )
        logger.info("daily-v2 normalization completed: normalized_rows=%d", len(normalized))
        persist_normalized_messages(conn, normalized)
        logger.info("daily-v2 normalized messages persisted")
        classified = classify_messages(normalized, taxonomy=taxonomy, provider=provider)
        logger.info("daily-v2 classification completed: classified_units=%d", len(classified))
        persist_classified_chunks(
            conn,
            normalized_messages=normalized,
            classified_messages=classified,
        )
        logger.info("daily-v2 classified chunks persisted")
        same_day_bundle = load_same_day_bundle(conn, date)
        report_artifact = synthesize_same_day_bundle(same_day_bundle)
        output_markdown = render_stock_report_markdown(report_artifact)
        report_run_id = persist_report_artifact(
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
