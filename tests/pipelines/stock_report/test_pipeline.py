from __future__ import annotations

from pathlib import Path

import pytest

from src.pipelines.stock_report.pipeline import run_daily_v2
from src.pipelines.stock_report.telegram_ingest import (
    TelegramIngestStats,
    discover_csv_files,
    parse_channel_key,
)


def test_discover_csv_files_loads_matching_day_files(tmp_path: Path):
    month_dir = tmp_path / "2026-05"
    month_dir.mkdir(parents=True)
    (month_dir / "2026-05-08-ked_epic_ai.csv").write_text(
        "message_id,timestamp,channel_name,author,content,media_info,forward_from\n",
        encoding="utf-8",
    )
    (month_dir / "2026-05-08-kwusa.csv").write_text(
        "message_id,timestamp,channel_name,author,content,media_info,forward_from\n",
        encoding="utf-8",
    )
    (month_dir / "2026-05-07-kwusa.csv").write_text(
        "message_id,timestamp,channel_name,author,content,media_info,forward_from\n",
        encoding="utf-8",
    )

    files = discover_csv_files("2026-05-08", str(tmp_path))

    assert [path.name for path in files] == [
        "2026-05-08-ked_epic_ai.csv",
        "2026-05-08-kwusa.csv",
    ]


def test_parse_channel_key_extracts_key_from_filename():
    csv_path = Path("2026-05-08-kiwoom_semibat.csv")
    assert parse_channel_key("2026-05-08", csv_path) == "kiwoom_semibat"


def test_run_daily_v2_calls_migration_and_ingest(monkeypatch):
    events: list[str] = []
    fake_conn = object()

    class _FakeContext:
        def __enter__(self):
            events.append("connect.enter")
            return fake_conn

        def __exit__(self, exc_type, exc, tb):
            events.append("connect.exit")
            return False

    def _fake_resolve_db_dsn(dsn):
        events.append(f"resolve_dsn:{dsn}")
        return "postgresql://fake-dsn"

    def _fake_connect_db(dsn):
        events.append(f"connect:{dsn}")
        return _FakeContext()

    def _fake_apply_migrations(conn, migrations_dir):
        events.append(f"migrate:{migrations_dir}")
        assert conn is fake_conn
        return ["001_phase1.sql"]

    def _fake_ingest(conn, date, data_dir):
        events.append(f"ingest:{date}:{data_dir}")
        assert conn is fake_conn
        return TelegramIngestStats(csv_files=2, parsed_rows=12, upserted_rows=11)

    monkeypatch.setattr("src.pipelines.stock_report.pipeline.resolve_db_dsn", _fake_resolve_db_dsn)
    monkeypatch.setattr("src.pipelines.stock_report.pipeline.connect_db", _fake_connect_db)
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.apply_migrations",
        _fake_apply_migrations,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.ingest_telegram_raw_csvs",
        _fake_ingest,
    )

    result = run_daily_v2(
        date="2026-05-08",
        data_dir="data",
        provider="openai",
        compare=False,
        dsn=None,
    )

    assert result.date == "2026-05-08"
    assert result.provider == "openai"
    assert result.compare is False
    assert result.csv_files == 2
    assert result.parsed_rows == 12
    assert result.upserted_rows == 11
    assert result.migrations_applied == ["001_phase1.sql"]
    assert events == [
        "resolve_dsn:None",
        "connect:postgresql://fake-dsn",
        "connect.enter",
        "migrate:migrations/stock_report",
        "ingest:2026-05-08:data",
        "connect.exit",
    ]


def test_run_daily_v2_raises_on_invalid_date():
    with pytest.raises(ValueError):
        run_daily_v2(date="2026/05/08")
