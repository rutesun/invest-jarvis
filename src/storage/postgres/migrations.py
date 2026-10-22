from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_checksum_migrations(
    conn: Any,
    migrations_dir: Path,
    *,
    history_table: str,
    bootstrap: Callable[[Any], None] | None = None,
) -> list[str]:
    if not migrations_dir.exists():
        raise FileNotFoundError(f"migration 디렉토리를 찾을 수 없습니다: {migrations_dir}")
    if bootstrap is not None:
        bootstrap(conn)
    else:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {history_table} (
                    filename TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()

    with conn.cursor() as cur:
        cur.execute(f"SELECT filename, checksum FROM {history_table}")
        applied = dict(cur.fetchall())

    applied_now: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        checksum = _checksum(path)
        previous = applied.get(path.name)
        if previous is not None:
            if previous != checksum:
                raise RuntimeError(f"이미 적용된 migration 파일이 변경되었습니다: {path.name}")
            continue
        try:
            with conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    f"INSERT INTO {history_table} (filename, checksum) VALUES (%s, %s)",
                    (path.name, checksum),
                )
            conn.commit()
            applied_now.append(path.name)
        except Exception:
            conn.rollback()
            raise
    return applied_now
