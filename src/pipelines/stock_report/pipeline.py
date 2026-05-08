from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.pipelines.stock_report.db import apply_migrations, connect_db, resolve_db_dsn
from src.pipelines.stock_report.telegram_ingest import TelegramIngestStats, ingest_telegram_raw_csvs


@dataclass(slots=True)
class DailyV2RunResult:
    date: str
    provider: str
    compare: bool
    csv_files: int
    parsed_rows: int
    upserted_rows: int
    migrations_applied: list[str]


def _validate_date(date: str) -> str:
    datetime.strptime(date, "%Y-%m-%d")
    return date


def run_daily_v2(
    date: str,
    data_dir: str = "data",
    provider: str = "openai",
    compare: bool = False,
    dsn: str | None = None,
    migrations_dir: str = "migrations/stock_report",
) -> DailyV2RunResult:
    _validate_date(date)
    resolved_dsn = resolve_db_dsn(dsn)
    migrations_path = Path(migrations_dir)

    with connect_db(resolved_dsn) as conn:
        migrations_applied = apply_migrations(conn, migrations_path)
        ingest_stats: TelegramIngestStats = ingest_telegram_raw_csvs(
            conn=conn,
            date=date,
            data_dir=data_dir,
        )

    return DailyV2RunResult(
        date=date,
        provider=provider,
        compare=compare,
        csv_files=ingest_stats.csv_files,
        parsed_rows=ingest_stats.parsed_rows,
        upserted_rows=ingest_stats.upserted_rows,
        migrations_applied=migrations_applied,
    )


def run_validate_v2(
    date: str,
    data_dir: str = "data",
    provider: str = "openai",
    dsn: str | None = None,
    migrations_dir: str = "migrations/stock_report",
) -> DailyV2RunResult:
    return run_daily_v2(
        date=date,
        data_dir=data_dir,
        provider=provider,
        compare=True,
        dsn=dsn,
        migrations_dir=migrations_dir,
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
    ]

    if result.migrations_applied:
        lines.append(f"- applied migrations: `{', '.join(result.migrations_applied)}`")
    else:
        lines.append("- applied migrations: `none`")

    return "\n".join(lines)
