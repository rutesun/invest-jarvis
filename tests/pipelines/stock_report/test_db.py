from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from src.pipelines.stock_report.db import (
    delete_document_chunks,
    get_document_by_content_hash,
    get_document_by_path,
    load_pending_document_chunks,
    persist_classified_chunks,
    persist_document_chunks,
    search_document_chunks,
    upsert_document,
)
from src.pipelines.stock_report.models import (
    ClassifiedMessage,
    EvidenceItem,
    NormalizedMessage,
    QAWarning,
)
from src.pipelines.stock_report.pdf_chunking import PdfChunkDraft
from src.pipelines.stock_report.pdf_metadata import DocumentMeta
from src.pipelines.stock_report.pdf_parser import ParsedDocument
from src.pipelines.stock_report.synthesize import ReportEvidenceRef


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.conn.executed.append((query, params))

    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        self.conn.executemany_calls.append((query, params))

    def fetchone(self) -> tuple[int]:
        return (123,)


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


def _normalized() -> NormalizedMessage:
    return NormalizedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        channel_key="hana_us_stock",
        source_channel_key="hana_us_stock",
        source_channel_name="하나증권",
        channel_message_id="1",
        raw_text="Seagate 주가 8% 하락",
        clean_text="Seagate 주가 8% 하락",
        urls=[],
        has_media=False,
        content_hash="hash",
        processing_mode="full",
        grouped_message_ids=[],
    )


def test_persist_classified_chunks_serializes_typed_evidence_and_warnings() -> None:
    conn = FakeConnection()
    normalized = _normalized()
    classified = ClassifiedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        channel_key="hana_us_stock",
        source_channel_key="hana_us_stock",
        processing_mode="full",
        structure_type="single_topic_deep",
        unit_index=0,
        message_type="signal",
        event_type="해석/전망",
        category_key="반도체",
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=["Seagate"],
        canonical_summary="Seagate 주가 하락",
        supporting_facts=["Seagate 주가는 8% 하락"],
        evidence_items=[EvidenceItem(kind="metric", text="Seagate 주가는 8% 하락")],
        qa_warnings=[QAWarning(code="missing_metric_candidate", detail="test")],
    )

    persist_classified_chunks(
        conn,
        normalized_messages=[normalized],
        classified_messages=[classified],
    )

    assert len(conn.executemany_calls) == 1
    query, params = conn.executemany_calls[0]
    assert "evidence_items" in query
    assert "qa_warnings" in query
    payload = params[0]
    assert json.loads(payload[15]) == ["Seagate 주가는 8% 하락"]
    assert json.loads(payload[16]) == [{"kind": "metric", "text": "Seagate 주가는 8% 하락"}]
    assert json.loads(payload[17]) == [{"code": "missing_metric_candidate", "detail": "test"}]
    assert conn.commits == 1


def test_persist_classified_chunks_preserves_report_runs_when_replacing_chunks() -> None:
    conn = FakeConnection()
    normalized = _normalized()
    classified = ClassifiedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        channel_key="hana_us_stock",
        source_channel_key="hana_us_stock",
        processing_mode="full",
        structure_type="single_topic_deep",
        unit_index=0,
        message_type="signal",
        event_type=None,
        category_key="반도체",
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        canonical_summary="Seagate 주가 하락",
        supporting_facts=[],
    )

    persist_classified_chunks(
        conn,
        normalized_messages=[normalized],
        classified_messages=[classified],
    )

    executed_sql = [query for query, _params in conn.executed]
    assert not any("DELETE FROM report_runs" in query for query in executed_sql)
    assert any("DELETE FROM knowledge_chunks" in query for query in executed_sql)


def test_persist_report_artifact_writes_run_and_evidence() -> None:
    from src.pipelines.stock_report.db import persist_report_artifact

    conn = FakeConnection()
    report_run_id = persist_report_artifact(
        conn,
        report_date=date(2026, 5, 26),
        provider="openai",
        output_markdown="# report",
        evidence_refs=[
            ReportEvidenceRef(
                section_key="category_summaries",
                item_key="반도체",
                knowledge_chunk_id=10,
                rank_score=1.0,
                knowledge_chunk_snapshot={
                    "id": 10,
                    "canonical_summary": "Seagate 주가 하락",
                },
            )
        ],
    )

    assert report_run_id == 123
    assert not any("DELETE FROM report_runs" in query for query, _params in conn.executed)
    run_query, run_params = conn.executed[0]
    assert "INSERT INTO report_runs" in run_query
    assert run_params == (date(2026, 5, 26), "v2", "openai", "success", "# report")
    evidence_query, evidence_params = conn.executemany_calls[0]
    assert "INSERT INTO report_evidence" in evidence_query
    assert "knowledge_chunk_snapshot" in evidence_query
    assert evidence_params[0][:5] == (123, "category_summaries", "반도체", 10, 1.0)
    assert json.loads(evidence_params[0][5]) == {
        "id": 10,
        "canonical_summary": "Seagate 주가 하락",
    }
    assert conn.commits == 1


# --- PDF ingest write-path tests (T15) -------------------------------------


class _FakeColumn:
    """psycopg cursor.description의 Column 최소 구현."""

    def __init__(self, name: str) -> None:
        self.name = name


class ConfigurableCursor:
    """fetchone/fetchall 반환값을 테스트에서 제어할 수 있는 cursor."""

    def __init__(self, conn: ConfigurableConnection) -> None:
        self.conn = conn

    def __enter__(self) -> ConfigurableCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.conn.executed.append((query, params))

    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        self.conn.executemany_calls.append((query, params))

    def fetchone(self) -> Any:
        return self.conn.fetchone_result

    def fetchall(self) -> list[Any]:
        return self.conn.fetchall_result

    @property
    def description(self) -> list[_FakeColumn]:
        return self.conn.description_result or []


class ConfigurableConnection:
    def __init__(
        self,
        *,
        fetchone_result: Any = None,
        fetchall_result: list[Any] | None = None,
        description_result: list[_FakeColumn] | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.commits = 0
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.description_result = description_result

    def cursor(self) -> ConfigurableCursor:
        return ConfigurableCursor(self)

    def commit(self) -> None:
        self.commits += 1


def _parsed_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="data/files/2026-06-02/hana_seagate.pdf",
        markdown="# Seagate\n본문 텍스트",
        page_count=4,
        text_char_count=1200,
        image_ref_count=2,
        parse_mode="local",
        json_blocks=None,
        warnings=["json 읽기 실패: boom"],
    )


def _document_meta() -> DocumentMeta:
    return DocumentMeta(
        broker_key="hana",
        broker_name="하나증권",
        title="Seagate",
        published_date=date(2026, 6, 2),
        target_ticker="STX.US",
        category_key="반도체",
        main_theme="HDD",
        parse_status="ok",
        needs_hybrid=False,
    )


def _pdf_chunk_draft(seq: int, *, is_table: bool = False) -> PdfChunkDraft:
    return PdfChunkDraft(
        section_path="Seagate > 실적",
        chunk_seq=seq,
        is_table=is_table,
        canonical_summary="Seagate 실적 요약",
        content_clean="Seagate 매출 8% 증가",
        embed_payload="채널: 하나증권\nSeagate 매출 8% 증가",
        ticker_tags=["STX.US"],
    )


def test_get_document_by_path_returns_idempotency_fields() -> None:
    conn = ConfigurableConnection(fetchone_result=(7, "hash-abc", "parser-1"))

    result = get_document_by_path(conn, "data/files/2026-06-02/hana_seagate.pdf")

    assert result == {"id": 7, "content_hash": "hash-abc", "parser_version": "parser-1"}
    query, params = conn.executed[0]
    assert "FROM documents" in query
    assert "WHERE source_path = %s" in query
    assert params == ("data/files/2026-06-02/hana_seagate.pdf",)
    assert conn.commits == 0


def test_get_document_by_path_returns_none_when_missing() -> None:
    conn = ConfigurableConnection(fetchone_result=None)

    result = get_document_by_path(conn, "missing.pdf")

    assert result is None


def test_get_document_by_content_hash_returns_id_and_path() -> None:
    conn = ConfigurableConnection(fetchone_result=(7, "data/files/2026-06-02/hana_seagate.pdf"))

    result = get_document_by_content_hash(conn, "hash-abc")

    assert result == {"id": 7, "source_path": "data/files/2026-06-02/hana_seagate.pdf"}
    query, params = conn.executed[0]
    assert "FROM documents" in query
    assert "WHERE content_hash = %s" in query
    assert params == ("hash-abc",)
    assert conn.commits == 0


def test_get_document_by_content_hash_returns_none_when_missing() -> None:
    conn = ConfigurableConnection(fetchone_result=None)

    assert get_document_by_content_hash(conn, "missing-hash") is None


def test_upsert_document_uses_on_conflict_source_path() -> None:
    conn = FakeConnection()

    document_id = upsert_document(
        conn,
        parsed=_parsed_document(),
        meta=_document_meta(),
        content_hash="hash-abc",
        parser_version="opendataloader-pdf-2.4.7",
    )

    assert document_id == 123
    query, _params = conn.executed[0]
    assert "INSERT INTO documents" in query
    assert "ON CONFLICT (source_path)" in query
    assert "RETURNING id" in query
    assert "updated_at = NOW()" in query
    # 호출자가 트랜잭션을 제어한다 — 적재 함수는 commit하지 않는다.
    assert conn.commits == 0


def test_upsert_document_serializes_warnings_jsonb() -> None:
    conn = FakeConnection()

    upsert_document(
        conn,
        parsed=_parsed_document(),
        meta=_document_meta(),
        content_hash="hash-abc",
        parser_version="opendataloader-pdf-2.4.7",
    )

    query, params = conn.executed[0]
    assert "%s::jsonb" in query
    # parse_warnings는 마지막 파라미터로 json 문자열 직렬화돼 들어간다.
    assert json.loads(params[-1]) == ["json 읽기 실패: boom"]
    # 핵심 메타/파싱 필드가 파라미터에 들어갔는지 확인.
    assert params[0] == "data/files/2026-06-02/hana_seagate.pdf"
    assert params[1] == "hash-abc"
    assert "하나증권" in params


def test_persist_document_chunks_batches_and_no_commit() -> None:
    conn = FakeConnection()
    drafts = [
        _pdf_chunk_draft(0),
        _pdf_chunk_draft(1, is_table=True),
    ]

    count = persist_document_chunks(
        conn,
        document_id=7,
        source_date=date(2026, 6, 2),
        broker_key="hana",
        category_key="반도체",
        main_theme="HDD",
        drafts=drafts,
    )

    assert count == 2
    assert len(conn.executemany_calls) == 1
    query, params = conn.executemany_calls[0]
    assert "INSERT INTO document_chunks" in query
    assert "%s::jsonb" in query
    assert len(params) == 2
    # ticker_tags(9번째 컬럼, 인덱스 8)는 jsonb 직렬화돼 들어간다.
    assert json.loads(params[0][8]) == ["STX.US"]
    # priority_score(마지막 컬럼): 산문 1.0, 표 1.2.
    assert params[0][-1] == 1.0
    assert params[1][-1] == 1.2
    # 호출자가 트랜잭션을 제어한다 — 적재 함수는 commit하지 않는다.
    assert conn.commits == 0


def test_persist_document_chunks_empty_returns_zero() -> None:
    conn = FakeConnection()

    count = persist_document_chunks(
        conn,
        document_id=7,
        source_date=date(2026, 6, 2),
        broker_key="hana",
        category_key="반도체",
        main_theme="HDD",
        drafts=[],
    )

    assert count == 0
    assert conn.executemany_calls == []
    assert conn.commits == 0


def test_delete_document_chunks_targets_document_id() -> None:
    conn = FakeConnection()

    delete_document_chunks(conn, 7)

    query, params = conn.executed[0]
    assert "DELETE FROM document_chunks WHERE document_id" in query
    assert params == (7,)
    assert conn.commits == 0


def test_load_pending_document_chunks_filters_status() -> None:
    rows = [(1, "payload-1"), (2, "payload-2")]

    # include_failed=False → pending만, 쿼리에 failed 미포함.
    conn_pending = ConfigurableConnection(fetchall_result=rows)
    result = load_pending_document_chunks(conn_pending, include_failed=False)
    assert result == rows
    query, params = conn_pending.executed[0]
    assert "embed_status IN (%s)" in query
    assert params == ("pending",)

    # include_failed=True → pending + failed.
    conn_both = ConfigurableConnection(fetchall_result=rows)
    load_pending_document_chunks(conn_both, include_failed=True)
    query_both, params_both = conn_both.executed[0]
    assert "embed_status IN (%s, %s)" in query_both
    assert params_both == ("pending", "failed")

    # document_id 지정 시 WHERE에 document_id 조건 + 파라미터.
    conn_doc = ConfigurableConnection(fetchall_result=rows)
    load_pending_document_chunks(conn_doc, document_id=7, include_failed=False)
    query_doc, params_doc = conn_doc.executed[0]
    assert "document_id = %s" in query_doc
    assert params_doc == ("pending", 7)
    assert conn_doc.commits == 0


# --- search_document_chunks -------------------------------------------------

_SEARCH_COLS = [
    "id",
    "document_id",
    "chunk_seq",
    "is_table",
    "section_path",
    "content_clean",
    "category_key",
    "main_theme",
    "ticker_tags",
    "doc_title",
    "source_path",
    "broker_key",
    "published_date",
    "similarity",
]


def _search_conn(rows: list[tuple[Any, ...]]) -> ConfigurableConnection:
    return ConfigurableConnection(
        fetchall_result=rows,
        description_result=[_FakeColumn(c) for c in _SEARCH_COLS],
    )


def test_search_document_chunks_maps_rows_to_dicts() -> None:
    row = (
        1,
        10,
        3,
        False,
        "intro",
        "HBM 관련 본문",
        "반도체",
        "HBM",
        [],
        "소부장 리포트",
        "data/files/doc.pdf",
        "shinhan",
        None,
        0.87,
    )
    conn = _search_conn([row])
    results = search_document_chunks(conn, [0.1] * 1536, top_k=5)
    assert len(results) == 1
    assert results[0]["doc_title"] == "소부장 리포트"
    assert results[0]["similarity"] == 0.87
    assert results[0]["category_key"] == "반도체"


def test_search_document_chunks_sql_contains_cte_and_dedup() -> None:
    conn = _search_conn([])
    search_document_chunks(conn, [0.0] * 1536, top_k=3)
    query, _ = conn.executed[0]
    assert "WITH ranked AS" in query
    assert "ROW_NUMBER() OVER" in query
    assert "PARTITION BY dc.document_id" in query
    assert "WHERE rn = 1" in query
    assert "LIMIT" in query


def test_search_document_chunks_category_filter_injected() -> None:
    conn = _search_conn([])
    search_document_chunks(conn, [0.0] * 1536, category_filter="반도체", top_k=3)
    query, params = conn.executed[0]
    assert "d.category_key" in query
    assert isinstance(params, dict)
    assert params.get("category") == "반도체"


def test_search_document_chunks_no_category_clause_when_none() -> None:
    conn = _search_conn([])
    search_document_chunks(conn, [0.0] * 1536, category_filter=None, top_k=5)
    query, params = conn.executed[0]
    assert "d.category_key" not in query
    assert isinstance(params, dict)
    assert params.get("category") is None


def test_search_document_chunks_ticker_filter_injected() -> None:
    conn = _search_conn([])
    search_document_chunks(conn, [0.0] * 1536, ticker_filter="005930.KS", top_k=3)
    query, params = conn.executed[0]
    assert "dc.ticker_tags @> %(ticker)s::jsonb" in query
    assert isinstance(params, dict)
    assert params.get("ticker") == json.dumps(["005930.KS"])


def test_search_document_chunks_no_ticker_clause_when_none() -> None:
    conn = _search_conn([])
    search_document_chunks(conn, [0.0] * 1536, ticker_filter=None, top_k=5)
    query, params = conn.executed[0]
    assert "@>" not in query
    assert isinstance(params, dict)
    assert "ticker" not in params


def test_search_document_chunks_category_and_ticker_both_anded() -> None:
    conn = _search_conn([])
    search_document_chunks(
        conn, [0.0] * 1536, category_filter="반도체", ticker_filter="005930.KS", top_k=3
    )
    query, params = conn.executed[0]
    assert "d.category_key = %(category)s" in query
    assert "dc.ticker_tags @> %(ticker)s::jsonb" in query
    assert params.get("category") == "반도체"
    assert params.get("ticker") == json.dumps(["005930.KS"])
