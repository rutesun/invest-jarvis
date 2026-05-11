from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from src.pipelines.stock_report.classify import classify_messages
from src.pipelines.stock_report.db import (
    apply_migrations,
    connect_db,
    load_telegram_messages_by_date,
    resolve_db_dsn,
)
from src.pipelines.stock_report.normalize import normalize_messages, persist_normalized_messages
from src.pipelines.stock_report.taxonomy import load_taxonomy_registry
from src.pipelines.stock_report.telegram_ingest import TelegramIngestStats, ingest_telegram_raw_csvs


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

    with connect_db(resolved_dsn) as conn:
        migrations_applied = apply_migrations(conn, migrations_path)
        ingest_stats: TelegramIngestStats = ingest_telegram_raw_csvs(
            conn=conn,
            date=date,
            data_dir=data_dir,
        )
        raw_messages = load_telegram_messages_by_date(conn, date)
        normalized = normalize_messages(
            raw_messages,
            short_comment_channels=short_channels,
            short_comment_max_chars=max_chars,
            group_window_minutes=group_window,
        )
        persist_normalized_messages(conn, normalized)
        classified = classify_messages(normalized, taxonomy=taxonomy, provider=provider)

    grouped_only_rows = sum(1 for row in normalized if row.processing_mode == "grouped_only")
    skipped_rows = sum(1 for row in normalized if row.processing_mode == "skip")
    message_type_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    preview_canonical_summaries: list[str] = []
    for row in classified:
        message_type_counts[row.message_type] = message_type_counts.get(row.message_type, 0) + 1
        category_counts[row.category_key] = category_counts.get(row.category_key, 0) + 1
        if row.canonical_summary != "-" and len(preview_canonical_summaries) < preview_limit:
            preview_canonical_summaries.append(
                f"[{row.message_type}] ({row.category_key}) {row.canonical_summary}"
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
