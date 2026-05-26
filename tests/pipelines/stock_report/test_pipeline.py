from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.pipelines.stock_report.models import (
    ClassifiedMessage,
    NormalizedMessage,
    RawTelegramMessage,
)
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

    def _fake_load_messages(conn, source_date):
        events.append(f"load_messages:{source_date}")
        assert conn is fake_conn
        return [
            RawTelegramMessage(
                id=101,
                source_date=date(2026, 5, 8),
                date_kst=date(2026, 5, 8),
                posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
                channel_key="hana_us_stock",
                channel_name="hana_us_stock",
                channel_message_id="1",
                author=None,
                raw_text="NVDA +2.5%",
                media_info=None,
                forward_from_channel_key=None,
                forward_from_channel_name=None,
            )
        ]

    def _fake_normalize(raw_messages, **kwargs):
        events.append(f"normalize:{len(raw_messages)}")
        return [
            NormalizedMessage(
                telegram_message_id=101,
                source_date=date(2026, 5, 8),
                date_kst=date(2026, 5, 8),
                posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
                channel_key="hana_us_stock",
                source_channel_key="hana_us_stock",
                source_channel_name="hana_us_stock",
                channel_message_id="1",
                raw_text="NVDA +2.5%",
                clean_text="NVDA +2.5%",
                urls=[],
                has_media=False,
                content_hash="abc",
                processing_mode="full",
                grouped_message_ids=[],
            )
        ]

    def _fake_persist(conn, normalized_messages):
        events.append(f"persist:{len(normalized_messages)}")
        assert conn is fake_conn

    def _fake_classify(normalized_messages, taxonomy, provider):
        events.append(f"classify:{len(normalized_messages)}")
        assert provider == "openai"
        return [
            ClassifiedMessage(
                telegram_message_id=101,
                source_date=date(2026, 5, 8),
                channel_key="hana_us_stock",
                source_channel_key="hana_us_stock",
                processing_mode="full",
                structure_type="single_topic_deep",
                unit_index=0,
                message_type="data",
                event_type="통계/지표",
                category_key="unclassified",
                main_theme=None,
                provisional_category="반도체",
                provisional_theme="메모리",
                is_provisional=True,
                sub_themes=[],
                ticker_tags=["NVDA"],
                canonical_summary="NVDA +2.5%",
                supporting_facts=[],
            )
        ]

    def _fake_persist_chunks(conn, *, normalized_messages, classified_messages):
        events.append(f"persist_chunks:{len(classified_messages)}")
        assert conn is fake_conn
        assert len(normalized_messages) == 1

    def _fake_load_same_day_bundle(conn, report_date):
        events.append(f"load_bundle:{report_date}")
        assert conn is fake_conn
        return SimpleNamespace(
            category_buckets=[
                SimpleNamespace(theme_buckets=[object()]),
            ],
            focus_ticker_buckets=[object()],
            low_confidence_chunks=[],
        )

    monkeypatch.setattr("src.pipelines.stock_report.pipeline.resolve_db_dsn", _fake_resolve_db_dsn)
    monkeypatch.setattr("src.pipelines.stock_report.pipeline.connect_db", _fake_connect_db)
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline._load_normalize_config",
        lambda *_args, **_kwargs: ({"hana_us_stock"}, 100, 30),
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.load_taxonomy_registry",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.apply_migrations",
        _fake_apply_migrations,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.ingest_telegram_raw_csvs",
        _fake_ingest,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.load_telegram_messages_by_date",
        _fake_load_messages,
    )
    monkeypatch.setattr("src.pipelines.stock_report.pipeline.normalize_messages", _fake_normalize)
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.persist_normalized_messages",
        _fake_persist,
    )
    monkeypatch.setattr("src.pipelines.stock_report.pipeline.classify_messages", _fake_classify)
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.persist_classified_chunks",
        _fake_persist_chunks,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.load_same_day_bundle",
        _fake_load_same_day_bundle,
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
    assert result.normalized_rows == 1
    assert result.grouped_only_rows == 0
    assert result.skipped_rows == 0
    assert result.message_type_counts == {"data": 1}
    assert result.category_counts == {"반도체": 1}
    assert result.category_bucket_count == 1
    assert result.theme_bucket_count == 1
    assert result.focus_ticker_count == 1
    assert result.low_confidence_count == 0
    assert result.preview_canonical_summaries == ["[data/통계/지표] (반도체) NVDA +2.5%"]
    assert result.migrations_applied == ["001_phase1.sql"]
    assert events == [
        "resolve_dsn:None",
        "connect:postgresql://fake-dsn",
        "connect.enter",
        "migrate:migrations/stock_report",
        "ingest:2026-05-08:data",
        "load_messages:2026-05-08",
        "normalize:1",
        "persist:1",
        "classify:1",
        "persist_chunks:1",
        "load_bundle:2026-05-08",
        "connect.exit",
    ]


def test_run_daily_v2_raises_on_invalid_date():
    with pytest.raises(ValueError):
        run_daily_v2(date="2026/05/08")
