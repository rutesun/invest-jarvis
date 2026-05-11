from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.pipelines.stock_report.models import RawTelegramMessage


MIGRATION_HISTORY_TABLE = "stock_report_migration_history"


def resolve_db_dsn(dsn: str | None = None) -> str:
    if dsn:
        return dsn

    for key in ("STOCK_REPORT_DB_DSN", "DATABASE_URL"):
        value = os.getenv(key)
        if value:
            return value

    raise ValueError("DB DSN이 없습니다. STOCK_REPORT_DB_DSN 또는 DATABASE_URL을 설정하세요.")


def _load_psycopg() -> Any:
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency/runtime guard
        raise RuntimeError("psycopg가 설치되지 않았습니다. `uv sync` 후 다시 실행하세요.") from exc
    return psycopg


@contextmanager
def connect_db(dsn: str) -> Iterator[Any]:
    psycopg = _load_psycopg()
    conn = psycopg.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def _ensure_migration_history_table(conn: Any) -> None:
    query = f"""
    CREATE TABLE IF NOT EXISTS {MIGRATION_HISTORY_TABLE} (
        filename TEXT PRIMARY KEY,
        checksum TEXT NOT NULL,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with conn.cursor() as cur:
        cur.execute(query)
    conn.commit()


def _load_applied_migrations(conn: Any) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT filename, checksum FROM {MIGRATION_HISTORY_TABLE}")
        rows = cur.fetchall()
    return dict(rows)


def _migration_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_migrations(conn: Any, migrations_dir: Path) -> list[str]:
    if not migrations_dir.exists():
        raise FileNotFoundError(f"migration 디렉토리를 찾을 수 없습니다: {migrations_dir}")

    _ensure_migration_history_table(conn)
    applied = _load_applied_migrations(conn)
    applied_now: list[str] = []

    for path in sorted(migrations_dir.glob("*.sql")):
        checksum = _migration_checksum(path)
        applied_checksum = applied.get(path.name)

        if applied_checksum:
            if applied_checksum != checksum:
                raise RuntimeError(f"이미 적용된 migration 파일이 변경되었습니다: {path.name}")
            continue

        sql = path.read_text(encoding="utf-8")
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    f"INSERT INTO {MIGRATION_HISTORY_TABLE} (filename, checksum) VALUES (%s, %s)",
                    (path.name, checksum),
                )
            conn.commit()
            applied_now.append(path.name)
        except Exception:
            conn.rollback()
            raise

    return applied_now


def load_telegram_messages_by_date(conn: Any, source_date: str) -> list[RawTelegramMessage]:
    query = """
    SELECT
        id,
        source_date,
        date_kst,
        posted_at,
        channel_key,
        channel_name,
        channel_message_id,
        author,
        raw_text,
        media_info,
        forward_from_channel_key,
        forward_from_channel_name
    FROM telegram_messages
    WHERE source_date = %s
    ORDER BY posted_at ASC, id ASC;
    """
    with conn.cursor() as cur:
        cur.execute(query, (source_date,))
        rows = cur.fetchall()

    messages: list[RawTelegramMessage] = []
    for row in rows:
        messages.append(
            RawTelegramMessage(
                id=row[0],
                source_date=row[1],
                date_kst=row[2],
                posted_at=row[3],
                channel_key=row[4],
                channel_name=row[5],
                channel_message_id=row[6],
                author=row[7],
                raw_text=row[8],
                media_info=row[9],
                forward_from_channel_key=row[10],
                forward_from_channel_name=row[11],
            )
        )
    return messages
