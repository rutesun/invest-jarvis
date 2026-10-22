from __future__ import annotations

from pathlib import Path

import pytest

from src.storage.postgres.connection import resolve_db_dsn
from src.storage.postgres.migrations import apply_checksum_migrations


class Cursor:
    def __init__(self, conn: Connection):
        self.conn = conn
        self.rows: list[tuple[str, str]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        self.conn.executed.append((" ".join(query.split()), params))
        if query.lstrip().startswith("SELECT filename, checksum"):
            self.rows = list(self.conn.applied.items())
        elif query.lstrip().startswith("INSERT INTO"):
            self.conn.applied[params[0]] = params[1]
        elif "FAIL" in query:
            raise RuntimeError("migration failed")

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self):
        self.applied: dict[str, str] = {}
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_resolve_db_dsn_uses_caller_order_and_explicit_value(monkeypatch):
    monkeypatch.setenv("JARVIS_DB_DSN", "postgresql://jarvis")
    monkeypatch.setenv("STOCK_REPORT_DB_DSN", "postgresql://stock")

    assert resolve_db_dsn(("JARVIS_DB_DSN", "STOCK_REPORT_DB_DSN")) == "postgresql://jarvis"
    assert resolve_db_dsn(("STOCK_REPORT_DB_DSN", "JARVIS_DB_DSN")) == "postgresql://stock"
    assert resolve_db_dsn(("JARVIS_DB_DSN",), explicit="postgresql://explicit") == (
        "postgresql://explicit"
    )


def test_checksum_runner_commits_history_before_each_migration(tmp_path: Path):
    (tmp_path / "002.sql").write_text("SELECT 2", encoding="utf-8")
    (tmp_path / "001.sql").write_text("SELECT 1", encoding="utf-8")
    conn = Connection()

    applied = apply_checksum_migrations(conn, tmp_path, history_table="history")

    assert applied == ["001.sql", "002.sql"]
    assert conn.commits == 3


def test_checksum_runner_rejects_changed_applied_file(tmp_path: Path):
    path = tmp_path / "001.sql"
    path.write_text("SELECT 1", encoding="utf-8")
    conn = Connection()
    apply_checksum_migrations(conn, tmp_path, history_table="history")
    path.write_text("SELECT changed", encoding="utf-8")

    with pytest.raises(RuntimeError, match="변경"):
        apply_checksum_migrations(conn, tmp_path, history_table="history")


def test_checksum_runner_rolls_back_only_failed_file(tmp_path: Path):
    (tmp_path / "001.sql").write_text("FAIL", encoding="utf-8")
    conn = Connection()

    with pytest.raises(RuntimeError, match="migration failed"):
        apply_checksum_migrations(conn, tmp_path, history_table="history")

    assert conn.commits == 1
    assert conn.rollbacks == 1
