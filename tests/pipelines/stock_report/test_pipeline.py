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
from src.pipelines.stock_report.pipeline import (
    _trace_final_report_inputs,
    _trace_final_report_outputs,
    _validate_date,
    run_daily_v2,
)
from src.pipelines.stock_report.synthesize import (
    ReportEvidenceRef,
    ReportSectionItem,
    StockReportArtifact,
)
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


def test_trace_final_report_inputs_summarizes_report_payloads_without_content():
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 8),
        pulse=[ReportSectionItem(key="pulse-1", title="SECRET TITLE", body="SECRET BODY")],
        category_summaries=[],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=["SECRET LOW CONFIDENCE"],
        evidence_refs=[
            ReportEvidenceRef(
                section_key="pulse",
                item_key="pulse-1",
                knowledge_chunk_id=123,
                rank_score=1.0,
                knowledge_chunk_snapshot={
                    "channel_name": "하나증권",
                    "channel_message_id": "9609",
                    "evidence_items": [{"text": "SECRET EVIDENCE"}],
                },
            )
        ],
    )
    markdown = "# Report\n\nSECRET REPORT BODY"

    payload = _trace_final_report_inputs(
        {
            "conn": object(),
            "report_artifact": artifact,
            "output_markdown": markdown,
            "evidence_refs": artifact.evidence_refs,
        }
    )

    payload_text = repr(payload)
    assert "SECRET TITLE" not in payload_text
    assert "SECRET BODY" not in payload_text
    assert "SECRET LOW CONFIDENCE" not in payload_text
    assert "SECRET EVIDENCE" not in payload_text
    assert "SECRET REPORT BODY" not in payload_text
    assert payload["conn"] == "<redacted:connection>"
    assert payload["report_artifact"]["type"] == "StockReportArtifact"
    assert payload["report_artifact"]["pulse_count"] == 1
    assert payload["output_markdown"]["chars"] == len(markdown)
    assert payload["evidence_refs"]["count"] == 1


def test_trace_final_report_outputs_summarizes_markdown_without_content():
    markdown = "# Report\n\nSECRET REPORT BODY"

    payload = _trace_final_report_outputs(markdown)

    assert "SECRET REPORT BODY" not in repr(payload)
    assert payload["type"] == "str"
    assert payload["chars"] == len(markdown)
    assert "sha256" in payload


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

    def _fake_classify(normalized_messages, taxonomy):
        events.append(f"classify:{len(normalized_messages)}")
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

    def _fake_synthesize_same_day_bundle(bundle, *, search_fn=None):
        events.append("synthesize_bundle")
        return SimpleNamespace(
            report_date=date(2026, 5, 8),
            evidence_refs=[object()],
            pdf_search_entries=[],
        )

    def _fake_render_stock_report_markdown(artifact):
        events.append("render_report")
        return "# rendered report"

    def _fake_persist_report_artifact(conn, **kwargs):
        events.append(f"persist_report:{kwargs['provider']}")
        assert conn is fake_conn
        assert kwargs["output_markdown"] == "# rendered report"
        assert len(kwargs["evidence_refs"]) == 1
        return 777

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
    monkeypatch.setattr("src.pipelines.stock_report.pipeline._stage_ingest", _fake_ingest)
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline._stage_load_raw_messages",
        _fake_load_messages,
    )
    monkeypatch.setattr("src.pipelines.stock_report.pipeline._stage_normalize", _fake_normalize)
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline._stage_persist_normalized",
        _fake_persist,
    )
    monkeypatch.setattr("src.pipelines.stock_report.pipeline._stage_classify", _fake_classify)
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline._stage_persist_chunks",
        _fake_persist_chunks,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline._stage_load_same_day_bundle",
        _fake_load_same_day_bundle,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.synthesize_daily",
        _fake_synthesize_same_day_bundle,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline._stage_render_markdown",
        _fake_render_stock_report_markdown,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline._stage_persist_report",
        _fake_persist_report_artifact,
    )

    result = run_daily_v2(
        date="2026-05-08",
        data_dir="data",
        dsn=None,
    )

    assert result.date == "2026-05-08"
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
    assert result.report_run_id == 777
    assert result.output_markdown == "# rendered report"
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
        "synthesize_bundle",
        "render_report",
        "persist_report:openai",
        "connect.exit",
    ]


def test_validate_date_normalizes_slash_separator():
    assert _validate_date("2026/05/08") == "2026-05-08"


def test_validate_date_raises_on_invalid_date():
    with pytest.raises(ValueError):
        _validate_date("2026/13/08")


# ---------------------------------------------------------------------------
# T17: Task 5 — pipeline edge 배선 테스트
# ---------------------------------------------------------------------------


def test_stage_local_evidence_synthesis_passes_search_fn(monkeypatch) -> None:
    """_stage_local_evidence_synthesis가 search_fn을 synthesize_daily에 전달한다."""
    from src.pipelines.stock_report.pipeline import _stage_local_evidence_synthesis

    captured: list[dict] = []

    def fake_synthesize_daily(bundle, *, search_fn=None):
        captured.append({"search_fn": search_fn})
        return SimpleNamespace(report_date=date(2026, 6, 22), evidence_refs=[])

    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.synthesize_daily",
        fake_synthesize_daily,
    )

    def fake_search_fn(query: str, **kwargs):
        return []

    bundle = SimpleNamespace()
    _stage_local_evidence_synthesis(bundle, search_fn=fake_search_fn)

    assert len(captured) == 1
    assert captured[0]["search_fn"] is fake_search_fn


def test_stage_local_evidence_synthesis_passes_none_when_no_search_fn(monkeypatch) -> None:
    """임베딩 키 부재 시 search_fn=None이 synthesize_daily에 전달된다."""
    from src.pipelines.stock_report.pipeline import _stage_local_evidence_synthesis

    captured: list[dict] = []

    def fake_synthesize_daily(bundle, *, search_fn=None):
        captured.append({"search_fn": search_fn})
        return SimpleNamespace(report_date=date(2026, 6, 22), evidence_refs=[])

    monkeypatch.setattr(
        "src.pipelines.stock_report.pipeline.synthesize_daily",
        fake_synthesize_daily,
    )

    bundle = SimpleNamespace()
    _stage_local_evidence_synthesis(bundle)

    assert captured[0]["search_fn"] is None


def test_summarize_evidence_refs_includes_pdf_info() -> None:
    """_summarize_evidence_refs_for_trace가 source_type별 카운트와 PDF document_chunk_id 샘플을 포함한다."""
    from src.pipelines.stock_report.pipeline import _summarize_evidence_refs_for_trace
    from src.pipelines.stock_report.synthesize import ReportEvidenceRef

    refs = [
        ReportEvidenceRef(
            section_key="category_summaries",
            item_key="반도체",
            knowledge_chunk_id=100,
            rank_score=1.0,
            knowledge_chunk_snapshot={
                "channel_name": "신한",
                "channel_message_id": "1",
                "channel_key": "shinhan",
            },
            source_type="telegram",
        ),
        ReportEvidenceRef(
            section_key="category_summaries",
            item_key="반도체",
            rank_score=0.9,
            knowledge_chunk_snapshot={"evidence_kind": "searched", "doc_title": "리포트"},
            source_type="pdf",
            document_chunk_id=9001,
        ),
    ]

    summary = _summarize_evidence_refs_for_trace(refs)

    assert summary["count"] == 2
    # source_type별 카운트
    assert summary.get("source_type_counts", {}).get("telegram") == 1
    assert summary.get("source_type_counts", {}).get("pdf") == 1
    # PDF document_chunk_id 샘플
    assert 9001 in summary.get("sample_document_chunk_ids", [])
