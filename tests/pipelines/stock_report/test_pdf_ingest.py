"""pdf_ingest 2-패스 오케스트레이션 단위 테스트 (T12).

외부 의존성(Java parse_pdfs, OpenAI embed_payloads)은 절대 실제로 호출하지 않는다 —
모두 monkeypatch한다. DB는 commit/rollback 카운터를 가진 FakeConnection으로 검증한다.

pdf_ingest는 ``from .db import upsert_document`` 식으로 import하므로, 패치 대상은
``src.pipelines.stock_report.pdf_ingest.<name>`` 네임스페이스다.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from src.pipelines.stock_report import pdf_ingest
from src.pipelines.stock_report.embed import EMBED_DIM
from src.pipelines.stock_report.pdf_chunking import PdfChunkDraft
from src.pipelines.stock_report.pdf_metadata import DocumentMeta
from src.pipelines.stock_report.pdf_parser import ParsedDocument


_MODULE = "src.pipelines.stock_report.pdf_ingest"


class FakeConnection:
    """commit/rollback 호출 횟수를 기록하는 가짜 커넥션."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Recorder:
    """패치된 함수들의 호출 인자를 기록하는 헬퍼."""

    def __init__(self) -> None:
        self.calls: dict[str, list[Any]] = {}

    def record(self, name: str, value: Any) -> None:
        self.calls.setdefault(name, []).append(value)

    def count(self, name: str) -> int:
        return len(self.calls.get(name, []))


def _parsed(source_path: str) -> ParsedDocument:
    return ParsedDocument(
        source_path=source_path,
        markdown="# Seagate\n본문 텍스트",
        page_count=4,
        text_char_count=1200,
        image_ref_count=2,
        parse_mode="local",
        json_blocks=None,
        warnings=[],
    )


def _meta(parse_status: str = "ok", published: date | None = date(2026, 6, 2)) -> DocumentMeta:
    return DocumentMeta(
        broker_key="hana",
        broker_name="하나증권",
        title="Seagate",
        published_date=published,
        target_ticker="STX.US",
        category_key="반도체",
        main_theme="HDD",
        parse_status=parse_status,
        needs_hybrid=False,
    )


def _draft(seq: int) -> PdfChunkDraft:
    return PdfChunkDraft(
        section_path="Seagate > 실적",
        chunk_seq=seq,
        is_table=False,
        canonical_summary="Seagate 실적",
        content_clean="Seagate 매출 8% 증가",
        embed_payload=f"payload-{seq}",
        ticker_tags=["STX.US"],
    )


def _patch_common(monkeypatch, conn: FakeConnection) -> _Recorder:
    """connect_db/apply_migrations/load_sources 등 공통 패치 + recorder 반환.

    개별 테스트는 반환된 recorder의 호출 기록을 검증하고, 필요하면 특정 함수를
    추가로 덮어쓴다(예외 주입 등).
    """
    rec = _Recorder()

    @contextmanager
    def _fake_connect_db(dsn: str):
        rec.record("connect_db", dsn)
        yield conn

    def _fake_apply_migrations(c: Any, migrations_dir: Any) -> list[str]:
        rec.record("apply_migrations", migrations_dir)
        assert c is conn
        return []

    monkeypatch.setattr(f"{_MODULE}.resolve_db_dsn", lambda dsn: dsn or "postgresql://fake")
    monkeypatch.setattr(f"{_MODULE}.connect_db", _fake_connect_db)
    monkeypatch.setattr(f"{_MODULE}.apply_migrations", _fake_apply_migrations)
    monkeypatch.setattr(f"{_MODULE}.load_sources", lambda path: {})

    # 기본값: get_document_by_path는 None(신규 문서), pending 없음.
    monkeypatch.setattr(f"{_MODULE}.get_document_by_path", lambda c, sp: None)
    monkeypatch.setattr(
        f"{_MODULE}.load_pending_document_chunks",
        lambda c, include_failed=True: [],
    )

    return rec


def _patch_parse(monkeypatch, rec: _Recorder, parsed_docs: list[ParsedDocument]) -> None:
    def _fake_parse_pdfs(paths, *, use_hybrid=False, ocr_lang=None, want_json=False):
        rec.record("parse_pdfs", {"paths": paths, "want_json": want_json})
        return parsed_docs

    monkeypatch.setattr(f"{_MODULE}.parse_pdfs", _fake_parse_pdfs)


def _patch_meta(monkeypatch, rec: _Recorder, metas: list[DocumentMeta]) -> None:
    iterator = iter(metas)

    def _fake_extract_metadata(parsed, source_path, sources):
        rec.record("extract_metadata", source_path)
        return next(iterator)

    monkeypatch.setattr(f"{_MODULE}.extract_metadata", _fake_extract_metadata)


def _patch_chunks(monkeypatch, rec: _Recorder, drafts: list[PdfChunkDraft]) -> None:
    def _fake_build_pdf_chunks(parsed, meta):
        rec.record("build_pdf_chunks", meta)
        return drafts

    monkeypatch.setattr(f"{_MODULE}.build_pdf_chunks", _fake_build_pdf_chunks)


def _patch_db_writes(monkeypatch, rec: _Recorder, *, persist_return: int = 2) -> None:
    def _fake_upsert_document(c, *, parsed, meta, content_hash, parser_version):
        rec.record(
            "upsert_document",
            {"source_path": parsed.source_path, "content_hash": content_hash},
        )
        return 7

    def _fake_delete_document_chunks(c, document_id):
        rec.record("delete_document_chunks", document_id)

    def _fake_persist_document_chunks(
        c, *, document_id, source_date, broker_key, category_key, main_theme, drafts
    ):
        rec.record(
            "persist_document_chunks",
            {"document_id": document_id, "source_date": source_date, "drafts": drafts},
        )
        return persist_return

    monkeypatch.setattr(f"{_MODULE}.upsert_document", _fake_upsert_document)
    monkeypatch.setattr(f"{_MODULE}.delete_document_chunks", _fake_delete_document_chunks)
    monkeypatch.setattr(f"{_MODULE}.persist_document_chunks", _fake_persist_document_chunks)


def _patch_embed(
    monkeypatch,
    rec: _Recorder,
    *,
    pending: list[tuple[int, str]] | None = None,
) -> None:
    if pending is not None:
        monkeypatch.setattr(
            f"{_MODULE}.load_pending_document_chunks",
            lambda c, include_failed=True: pending,
        )

    def _fake_embed_payloads(payloads):
        rec.record("embed_payloads", payloads)
        return [[0.0] * EMBED_DIM for _ in payloads]

    def _fake_upsert_embeddings(c, *, table, rows, **kwargs):
        rec.record("upsert_embeddings", {"table": table, "rows": rows})
        return len(rows)

    monkeypatch.setattr(f"{_MODULE}.embed_payloads", _fake_embed_payloads)
    monkeypatch.setattr(f"{_MODULE}.upsert_embeddings", _fake_upsert_embeddings)


def _make_pdf_dir(tmp_path, *names: str):
    for name in names:
        (tmp_path / name).write_bytes(b"%PDF-fake")
    return str(tmp_path)


def test_happy_path_two_pass(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf")

    _patch_parse(monkeypatch, rec, [_parsed(f"{input_dir}/a.pdf")])
    _patch_meta(monkeypatch, rec, [_meta()])
    _patch_chunks(monkeypatch, rec, [_draft(0), _draft(1)])
    _patch_db_writes(monkeypatch, rec, persist_return=2)
    _patch_embed(monkeypatch, rec, pending=[(101, "p0"), (102, "p1")])

    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir)

    assert summary.total_pdfs == 1
    assert summary.documents_upserted == 1
    assert summary.chunks_inserted == 2
    assert summary.embedded == 2
    assert summary.skipped == 0
    assert summary.failed == 0
    # 패스1: 문서 1건 적재 + 청킹.
    assert rec.count("upsert_document") == 1
    assert rec.count("persist_document_chunks") == 1
    # 패스2: 임베딩 호출.
    assert rec.count("embed_payloads") == 1
    assert rec.count("upsert_embeddings") == 1
    # 문서 단위 commit(1) + 패스2 commit(1) = 2.
    assert conn.commits == 2
    assert conn.rollbacks == 0
    # want_json=True로 파싱(needs_hybrid 판정 정확도).
    assert rec.calls["parse_pdfs"][0]["want_json"] is True


def test_idempotent_skip(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf")

    parsed = _parsed(f"{input_dir}/a.pdf")
    _patch_parse(monkeypatch, rec, [parsed])
    _patch_meta(monkeypatch, rec, [_meta()])
    _patch_chunks(monkeypatch, rec, [_draft(0)])
    _patch_db_writes(monkeypatch, rec)
    _patch_embed(monkeypatch, rec)

    # 기존 문서가 같은 content_hash + parser_version → skip.
    expected_hash = pdf_ingest._content_hash(Path(parsed.source_path))
    monkeypatch.setattr(
        f"{_MODULE}.get_document_by_path",
        lambda c, sp: {
            "id": 7,
            "content_hash": expected_hash,
            "parser_version": pdf_ingest.PARSER_VERSION,
        },
    )

    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir)

    assert summary.skipped == 1
    assert summary.documents_upserted == 0
    assert summary.chunks_inserted == 0
    assert rec.count("upsert_document") == 0
    assert rec.count("persist_document_chunks") == 0
    assert conn.commits == 0


def test_failed_status_skips_chunks(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf")

    _patch_parse(monkeypatch, rec, [_parsed(f"{input_dir}/a.pdf")])
    _patch_meta(monkeypatch, rec, [_meta(parse_status="failed")])
    _patch_chunks(monkeypatch, rec, [_draft(0)])
    _patch_db_writes(monkeypatch, rec)
    _patch_embed(monkeypatch, rec)

    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir)

    assert summary.failed == 1
    assert summary.documents_upserted == 1
    assert summary.chunks_inserted == 0
    # 문서는 기록하되 청크는 생략.
    assert rec.count("upsert_document") == 1
    assert rec.count("persist_document_chunks") == 0
    # failed 문서도 documents에 commit(1회).
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_needs_ocr_low_confidence(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf")

    _patch_parse(monkeypatch, rec, [_parsed(f"{input_dir}/a.pdf")])
    _patch_meta(monkeypatch, rec, [_meta(parse_status="needs_ocr")])
    _patch_chunks(monkeypatch, rec, [_draft(0)])
    _patch_db_writes(monkeypatch, rec)
    _patch_embed(monkeypatch, rec)

    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir)

    assert summary.low_confidence == 1
    assert summary.documents_upserted == 1
    assert summary.chunks_inserted == 0
    assert rec.count("persist_document_chunks") == 0
    assert conn.commits == 1


def test_document_transaction_rollback_continues(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf", "b.pdf")

    docs = [_parsed(f"{input_dir}/a.pdf"), _parsed(f"{input_dir}/b.pdf")]
    _patch_parse(monkeypatch, rec, docs)
    _patch_meta(monkeypatch, rec, [_meta(), _meta()])
    _patch_chunks(monkeypatch, rec, [_draft(0)])
    _patch_db_writes(monkeypatch, rec)
    _patch_embed(monkeypatch, rec, pending=[(101, "p0")])

    # 첫 문서의 persist는 예외, 두 번째는 정상.
    calls = {"n": 0}

    def _persist_boom(c, *, document_id, source_date, broker_key, category_key, main_theme, drafts):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        rec.record("persist_document_chunks", {"document_id": document_id})
        return 1

    monkeypatch.setattr(f"{_MODULE}.persist_document_chunks", _persist_boom)

    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir)

    # 배치 중단 안 함: 첫 문서 실패, 두 번째 정상.
    assert summary.failed == 1
    assert summary.documents_upserted == 2  # 둘 다 upsert는 호출됨
    assert summary.chunks_inserted == 1  # 두 번째만 적재
    assert conn.rollbacks == 1  # 첫 문서 롤백
    # 두 번째 문서 commit(1) + 패스2 commit(1) = 2.
    assert conn.commits == 2


def test_embed_missing_only_runs_pass2(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf")

    # parse_pdfs를 패치하되, 호출되면 실패하도록 감시.
    def _parse_should_not_run(*args, **kwargs):
        raise AssertionError("embed_missing=True인데 parse_pdfs가 호출됨")

    monkeypatch.setattr(f"{_MODULE}.parse_pdfs", _parse_should_not_run)
    _patch_embed(monkeypatch, rec, pending=[(101, "p0"), (102, "p1"), (103, "p2")])

    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir, embed_missing=True)

    assert summary.total_pdfs == 0
    assert summary.documents_upserted == 0
    assert summary.embedded == 3
    assert rec.count("parse_pdfs") == 0
    assert rec.count("embed_payloads") == 1
    assert rec.count("upsert_embeddings") == 1
    # 패스2 commit만(1회).
    assert conn.commits == 1


def test_embed_failure_keeps_pending(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf")

    _patch_parse(monkeypatch, rec, [_parsed(f"{input_dir}/a.pdf")])
    _patch_meta(monkeypatch, rec, [_meta()])
    _patch_chunks(monkeypatch, rec, [_draft(0)])
    _patch_db_writes(monkeypatch, rec, persist_return=1)
    monkeypatch.setattr(
        f"{_MODULE}.load_pending_document_chunks",
        lambda c, include_failed=True: [(101, "p0")],
    )

    def _embed_boom(payloads):
        raise RuntimeError("openai down")

    monkeypatch.setattr(f"{_MODULE}.embed_payloads", _embed_boom)
    monkeypatch.setattr(
        f"{_MODULE}.upsert_embeddings",
        lambda c, **kwargs: (_ for _ in ()).throw(AssertionError("실패 시 upsert 호출 금지")),
    )

    # 예외가 전파되지 않고 summary가 정상 반환돼야 한다.
    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir)

    assert summary.embedded == 0
    assert summary.documents_upserted == 1
    assert summary.chunks_inserted == 1
    # 패스1 문서 commit(1) + 패스2 임베딩 실패 rollback(1).
    assert conn.commits == 1
    assert conn.rollbacks == 1


def test_empty_directory_returns_zero_summary(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)

    def _parse_should_not_run(*args, **kwargs):
        raise AssertionError("빈 디렉토리인데 parse_pdfs가 호출됨")

    monkeypatch.setattr(f"{_MODULE}.parse_pdfs", _parse_should_not_run)
    _patch_embed(monkeypatch, rec)  # pending 없음

    # 빈 tmp_path(파일 없음).
    summary = pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=str(tmp_path))

    assert summary.total_pdfs == 0
    assert summary.documents_upserted == 0
    assert summary.chunks_inserted == 0
    assert summary.embedded == 0
    assert summary.failed == 0
    assert rec.count("parse_pdfs") == 0
    assert conn.commits == 0


def test_source_date_falls_back_to_arg_date(tmp_path, monkeypatch) -> None:
    conn = FakeConnection()
    rec = _patch_common(monkeypatch, conn)
    input_dir = _make_pdf_dir(tmp_path, "a.pdf")

    _patch_parse(monkeypatch, rec, [_parsed(f"{input_dir}/a.pdf")])
    # published_date=None → 인자 date로 폴백.
    _patch_meta(monkeypatch, rec, [_meta(published=None)])
    _patch_chunks(monkeypatch, rec, [_draft(0)])
    _patch_db_writes(monkeypatch, rec, persist_return=1)
    _patch_embed(monkeypatch, rec, pending=[(101, "p0")])

    pdf_ingest.run_ingest_pdf("2026-06-02", input_dir=input_dir)

    persist_call = rec.calls["persist_document_chunks"][0]
    assert persist_call["source_date"] == date(2026, 6, 2)
