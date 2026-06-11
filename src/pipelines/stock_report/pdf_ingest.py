"""PDF 인제스트 오케스트레이션 — 2-패스 파이프라인 (T12).

증권사 PDF를 ``documents`` + ``document_chunks``에 적재하고 임베딩한다. 앞단 모듈
(``pdf_parser``/``pdf_metadata``/``pdf_chunking``/``db``/``embed``)을 묶는 제어 흐름만
담당한다. 핵심 설계는 두 가지다.

1. **문서 단위 원자적 트랜잭션**: 패스1은 문서 하나를 파스→메타→upsert→청킹까지
   처리하고 그 문서만 commit한다. 한 문서가 실패하면 rollback하고 다음 문서로 계속
   진행한다(배치 전체를 중단하지 않는다).
2. **2-패스(임베딩을 트랜잭션 밖으로)**: 외부 API(OpenAI 임베딩)를 DB 트랜잭션 안에
   넣지 않는다. 패스1에서 청크를 ``embed_status='pending'``으로 먼저 커밋하고, 패스2가
   pending/failed 청크만 모아 임베딩한 뒤 별도로 커밋한다. 임베딩이 실패해도 청크는
   살아있고 다음 ``--embed-missing`` 실행에서 재시도된다.

멱등성: ``documents.content_hash`` + ``parser_version``이 모두 같으면 재파스를
건너뛴다(stale 벡터 방지). ``--reembed``는 이 체크를 무시하고 전체를 재적재한다.

트랜잭션 경계 계약: ``db``/``embed`` 적재 함수들은 commit/rollback을 호출하지 않는다.
경계 제어는 전적으로 이 모듈의 책임이다.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.pipelines.stock_report.db import (
    apply_migrations,
    connect_db,
    delete_document_chunks,
    get_document_by_content_hash,
    get_document_by_path,
    load_pending_document_chunks,
    persist_document_chunks,
    resolve_db_dsn,
    upsert_document,
)
from src.pipelines.stock_report.embed import embed_payloads, upsert_embeddings
from src.pipelines.stock_report.pdf_chunking import build_pdf_chunks
from src.pipelines.stock_report.pdf_metadata import extract_metadata, load_sources
from src.pipelines.stock_report.pdf_parser import PARSER_VERSION, parse_pdfs


logger = logging.getLogger(__name__)

_DOCUMENT_CHUNKS_TABLE = "document_chunks"


@dataclass(slots=True)
class IngestSummary:
    total_pdfs: int
    documents_upserted: int
    chunks_inserted: int
    embedded: int
    skipped: int  # 멱등 skip (같은 source_path, content_hash + parser_version 동일)
    duplicates: int  # 중복 skip (다른 source_path, content_hash 동일 — 같은 내용 재적재)
    low_confidence: int  # parse_status == 'needs_ocr'
    failed: int  # parse_status == 'failed' 또는 문서 트랜잭션 예외


def _validate_date(value: str) -> str:
    normalized = value.strip().replace("/", "-")
    datetime.strptime(normalized, "%Y-%m-%d")
    return normalized


def _content_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _date_from_str(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def run_ingest_pdf(
    date: str,
    input_dir: str | None = None,
    *,
    dsn: str | None = None,
    migrations_dir: str = "migrations/stock_report",
    sources_path: str = "config/stock_report_pdf_sources.yaml",
    use_hybrid: bool = False,
    ocr_lang: str | None = None,
    reembed: bool = False,
    embed_missing: bool = False,
) -> IngestSummary:
    """증권사 PDF를 documents/document_chunks에 적재하고 임베딩한다 (2-패스).

    embed_missing=True면 패스1(스캔/파싱)을 건너뛰고 곧장 패스2로 가서 pending/failed
    청크만 임베딩한다(하루치 backfill 재시도 경로).
    """
    date = _validate_date(date)
    resolved_dsn = resolve_db_dsn(dsn)
    input_dir = input_dir or f"data/files/{date}"

    summary = IngestSummary(
        total_pdfs=0,
        documents_upserted=0,
        chunks_inserted=0,
        embedded=0,
        skipped=0,
        duplicates=0,
        low_confidence=0,
        failed=0,
    )

    logger.info(
        "ingest-pdf started: date=%s input_dir=%s use_hybrid=%s embed_missing=%s reembed=%s",
        date,
        input_dir,
        use_hybrid,
        embed_missing,
        reembed,
    )

    with connect_db(resolved_dsn) as conn:
        migrations_applied = apply_migrations(conn, Path(migrations_dir))
        logger.info("ingest-pdf migrations applied: %s", migrations_applied or ["none"])

        if not embed_missing:
            _run_pass1(
                conn,
                date=date,
                input_dir=input_dir,
                sources_path=sources_path,
                use_hybrid=use_hybrid,
                ocr_lang=ocr_lang,
                reembed=reembed,
                summary=summary,
            )

        _run_pass2(conn, summary=summary)

    logger.info(
        "ingest-pdf finished: pdfs=%d documents=%d chunks=%d embedded=%d "
        "skipped=%d duplicates=%d low_confidence=%d failed=%d",
        summary.total_pdfs,
        summary.documents_upserted,
        summary.chunks_inserted,
        summary.embedded,
        summary.skipped,
        summary.duplicates,
        summary.low_confidence,
        summary.failed,
    )
    return summary


def _run_pass1(
    conn,
    *,
    date: str,
    input_dir: str,
    sources_path: str,
    use_hybrid: bool,
    ocr_lang: str | None,
    reembed: bool,
    summary: IngestSummary,
) -> None:
    """패스 1 — 파스→메타→upsert→청킹. 문서 단위로 commit/rollback한다."""
    sources = load_sources(sources_path)

    pdf_paths = sorted(Path(input_dir).glob("*.pdf"))
    summary.total_pdfs = len(pdf_paths)
    if not pdf_paths:
        logger.info("ingest-pdf no PDFs found in %s", input_dir)
        return

    parsed_docs = parse_pdfs(
        [str(p) for p in pdf_paths],
        use_hybrid=use_hybrid,
        ocr_lang=ocr_lang,
        want_json=True,
    )

    fallback_date = _date_from_str(date)
    seen_hashes: dict[str, str] = {}  # content_hash -> 먼저 채택한 source_path (배치 내 중복 차단)

    for parsed in parsed_docs:
        source_path = parsed.source_path
        content_hash = _content_hash(Path(source_path))

        if not reembed and _is_idempotent_skip(conn, source_path, content_hash):
            summary.skipped += 1
            logger.info("ingest-pdf skip (unchanged): %s", source_path)
            continue

        duplicate_of = _find_duplicate_path(conn, source_path, content_hash, seen_hashes)
        if duplicate_of is not None:
            summary.duplicates += 1
            logger.info("ingest-pdf skip (duplicate of %s): %s", duplicate_of, source_path)
            continue
        if content_hash:
            seen_hashes[content_hash] = source_path

        meta = extract_metadata(parsed, source_path, sources)

        try:
            document_id = upsert_document(
                conn,
                parsed=parsed,
                meta=meta,
                content_hash=content_hash,
                parser_version=PARSER_VERSION,
            )
            summary.documents_upserted += 1

            if meta.parse_status == "failed":
                summary.failed += 1
                conn.commit()
                logger.warning("ingest-pdf parse failed (document only): %s", source_path)
                continue

            if meta.parse_status == "needs_ocr":
                summary.low_confidence += 1
                conn.commit()
                logger.info("ingest-pdf needs_ocr (document only): %s", source_path)
                continue

            delete_document_chunks(conn, document_id)
            drafts = build_pdf_chunks(parsed, meta)
            source_date = meta.published_date or fallback_date
            inserted = persist_document_chunks(
                conn,
                document_id=document_id,
                source_date=source_date,
                broker_key=meta.broker_key,
                category_key=meta.category_key,
                main_theme=meta.main_theme,
                drafts=drafts,
            )
            summary.chunks_inserted += inserted
            conn.commit()
            logger.info("ingest-pdf document committed: %s (chunks=%d)", source_path, inserted)
        except Exception:
            conn.rollback()
            summary.failed += 1
            logger.warning("ingest-pdf document transaction failed: %s", source_path, exc_info=True)
            continue


def _is_idempotent_skip(conn, source_path: str, content_hash: str) -> bool:
    """기존 문서가 같은 content_hash + parser_version이면 재적재를 건너뛴다."""
    existing = get_document_by_path(conn, source_path)
    return (
        existing is not None
        and existing["content_hash"] == content_hash
        and existing["parser_version"] == PARSER_VERSION
    )


def _find_duplicate_path(
    conn,
    source_path: str,
    content_hash: str,
    seen_hashes: dict[str, str],
) -> str | None:
    """같은 내용(content_hash)이 다른 source_path로 이미 존재하면 그 경로를 반환한다.

    같은 증권사 리포트가 여러 채널(broker_key)로 들어와 파일명만 다른 경우를 막는다.
    배치 내 먼저 채택한 문서(seen_hashes)와 DB에 적재된 다른 경로 문서를 모두 본다.
    reembed와 무관하게 항상 적용한다(중복은 재적재 모드에서도 쌓이면 안 된다).
    content_hash가 비면(파일 읽기 실패) 중복 판정에서 제외한다.
    """
    if not content_hash:
        return None
    batch_duplicate = seen_hashes.get(content_hash)
    if batch_duplicate is not None:
        return batch_duplicate
    existing = get_document_by_content_hash(conn, content_hash)
    if existing is not None and existing["source_path"] != source_path:
        return existing["source_path"]
    return None


def _run_pass2(conn, *, summary: IngestSummary) -> None:
    """패스 2 — pending/failed 청크를 임베딩한다 (OpenAI 호출은 트랜잭션 밖).

    하루치 전체를 한 번에 처리한다(document_id 한정 없음). 969개 backfill의 스트리밍
    처리는 별도 작업이며, 여기서는 하루치(수천 청크) 일괄 처리로 충분하다.
    """
    pending = load_pending_document_chunks(conn, include_failed=True)
    if not pending:
        logger.info("ingest-pdf no pending chunks to embed")
        return

    chunk_ids = [row[0] for row in pending]
    payloads = [row[1] for row in pending]

    try:
        vectors = embed_payloads(payloads)
        rows = list(zip(chunk_ids, vectors, strict=True))
        embedded = upsert_embeddings(conn, table=_DOCUMENT_CHUNKS_TABLE, rows=rows)
        conn.commit()
        summary.embedded += embedded
        logger.info("ingest-pdf embedded chunks: %d", embedded)
    except Exception:
        conn.rollback()
        logger.warning(
            "ingest-pdf embedding failed (pending kept for retry): pending=%d",
            len(pending),
            exc_info=True,
        )
