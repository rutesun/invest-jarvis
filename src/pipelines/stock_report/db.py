from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from src.pipelines.stock_report.chunking import (
    KNOWLEDGE_CHUNK_SOURCE_TYPE,
    build_chunk_drafts,
)
from src.pipelines.stock_report.models import (
    ClassifiedMessage,
    NormalizedMessage,
    RawTelegramMessage,
)
from src.pipelines.stock_report.pdf_chunking import PdfChunkDraft
from src.pipelines.stock_report.pdf_metadata import DocumentMeta
from src.pipelines.stock_report.pdf_parser import ParsedDocument
from src.pipelines.stock_report.synthesize import ReportEvidenceRef


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


def persist_classified_chunks(
    conn: Any,
    *,
    normalized_messages: list[NormalizedMessage],
    classified_messages: list[ClassifiedMessage],
) -> None:
    if not normalized_messages:
        return

    source_dates = sorted({row.source_date for row in normalized_messages})
    with conn.cursor() as cur:
        for source_date in source_dates:
            cur.execute(
                """
                DELETE FROM knowledge_chunks
                WHERE source_type = %s
                  AND source_date = %s;
                """,
                (KNOWLEDGE_CHUNK_SOURCE_TYPE, source_date),
            )

    chunk_drafts = build_chunk_drafts(
        normalized_messages=normalized_messages,
        classified_messages=classified_messages,
    )

    if not chunk_drafts:
        conn.commit()
        return

    query = """
    INSERT INTO knowledge_chunks (
        source_type,
        source_pk,
        source_date,
        channel_key,
        message_type,
        event_type,
        category_key,
        main_theme,
        provisional_category,
        provisional_theme,
        is_provisional,
        sub_themes,
        ticker_tags,
        theme_tags,
        canonical_summary,
        supporting_facts,
        evidence_items,
        qa_warnings,
        content_clean,
        embed_payload,
        channel_weight,
        priority_score
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s::jsonb, %s::jsonb, %s::jsonb, %s,
        %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s
    );
    """

    params: list[tuple[Any, ...]] = []
    for draft in chunk_drafts:
        params.append(
            (
                draft.source_type,
                draft.source_pk,
                draft.source_date,
                draft.channel_key,
                draft.message_type,
                draft.event_type,
                draft.category_key,
                draft.main_theme,
                draft.provisional_category,
                draft.provisional_theme,
                draft.is_provisional,
                json.dumps(draft.sub_themes, ensure_ascii=False),
                json.dumps(draft.ticker_tags, ensure_ascii=False),
                json.dumps(draft.theme_tags, ensure_ascii=False),
                draft.canonical_summary,
                json.dumps(draft.supporting_facts, ensure_ascii=False),
                json.dumps(
                    [item.model_dump() for item in draft.evidence_items],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [warning.model_dump(exclude_none=True) for warning in draft.qa_warnings],
                    ensure_ascii=False,
                ),
                draft.content_clean,
                draft.embed_payload,
                draft.channel_weight,
                draft.priority_score,
            )
        )

    with conn.cursor() as cur:
        cur.executemany(query, params)
    conn.commit()


def persist_report_artifact(
    conn: Any,
    *,
    report_date: Any,
    provider: str,
    output_markdown: str,
    evidence_refs: list[ReportEvidenceRef],
    pipeline_version: str = "v2",
    status: str = "success",
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO report_runs (
                report_date,
                pipeline_version,
                provider,
                status,
                output_markdown
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (report_date, pipeline_version, provider, status, output_markdown),
        )
        report_run_id = cur.fetchone()[0]

        if evidence_refs:
            cur.executemany(
                """
                INSERT INTO report_evidence (
                    report_run_id,
                    section_key,
                    item_key,
                    knowledge_chunk_id,
                    rank_score,
                    knowledge_chunk_snapshot
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb);
                """,
                [
                    (
                        report_run_id,
                        ref.section_key,
                        ref.item_key,
                        ref.knowledge_chunk_id,
                        ref.rank_score,
                        json.dumps(ref.knowledge_chunk_snapshot, ensure_ascii=False),
                    )
                    for ref in evidence_refs
                ],
            )
    conn.commit()
    return report_run_id


# --- PDF ingest write-path (T15) -------------------------------------------
#
# 아래 함수들은 텔레그램 경로(persist_classified_chunks)와 의도적으로 다르게
# **conn.commit()을 호출하지 않는다**. PDF 인제스트는 "문서 단위 원자적 트랜잭션 +
# 2-패스(임베딩을 트랜잭션 밖으로)"가 요구사항이라 트랜잭션 경계를 호출자(다음
# 단계 pdf_ingest)가 제어해야 한다. 따라서 이 함수들은 cursor 작업만 수행한다.


def get_document_by_path(conn: Any, source_path: str) -> dict | None:
    """source_path로 기존 문서의 멱등성 판단 필드를 조회한다.

    반환: {"id", "content_hash", "parser_version"} 또는 None.
    호출자(ingest)가 content_hash/parser_version 변경 여부로 재파스/skip을 판단한다.
    commit은 호출자 책임(이 함수는 조회만, 트랜잭션 경계 제어 안 함).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, content_hash, parser_version
            FROM documents
            WHERE source_path = %s;
            """,
            (source_path,),
        )
        row = cur.fetchone()

    if row is None:
        return None
    return {"id": row[0], "content_hash": row[1], "parser_version": row[2]}


def get_document_by_content_hash(conn: Any, content_hash: str) -> dict | None:
    """content_hash로 기존 문서를 조회한다 (중복 적재 차단용).

    같은 내용(content_hash)의 PDF가 다른 source_path(다른 채널/파일명)로 이미
    적재됐는지 판단한다. source_path 기준 멱등 체크(get_document_by_path)와 달리,
    경로가 달라도 내용이 같으면 중복으로 본다. 반환: {"id", "source_path"} 또는 None.
    commit은 호출자 책임.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source_path
            FROM documents
            WHERE content_hash = %s
            ORDER BY id
            LIMIT 1;
            """,
            (content_hash,),
        )
        row = cur.fetchone()

    if row is None:
        return None
    return {"id": row[0], "source_path": row[1]}


def upsert_document(
    conn: Any,
    *,
    parsed: ParsedDocument,
    meta: DocumentMeta,
    content_hash: str,
    parser_version: str,
) -> int:
    """documents에 1행 upsert하고 document_id를 반환한다 (commit 안 함).

    source_path UNIQUE 충돌 시 메타/파싱 결과/해시를 갱신(updated_at=NOW()).
    parse_status='failed'/'needs_ocr' 문서도 documents에는 기록한다(청크는 호출자가 건너뜀).
    트랜잭션 경계는 호출자(pdf_ingest)가 제어한다 — 여기서 conn.commit()을 호출하지 않는다.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (
                source_path,
                content_hash,
                broker_key,
                broker_name,
                title,
                published_date,
                target_ticker,
                category_key,
                main_theme,
                page_count,
                parse_mode,
                parser_version,
                parse_status,
                needs_hybrid,
                text_char_count,
                markdown,
                parse_warnings
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (source_path) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                broker_key = EXCLUDED.broker_key,
                broker_name = EXCLUDED.broker_name,
                title = EXCLUDED.title,
                published_date = EXCLUDED.published_date,
                target_ticker = EXCLUDED.target_ticker,
                category_key = EXCLUDED.category_key,
                main_theme = EXCLUDED.main_theme,
                page_count = EXCLUDED.page_count,
                parse_mode = EXCLUDED.parse_mode,
                parser_version = EXCLUDED.parser_version,
                parse_status = EXCLUDED.parse_status,
                needs_hybrid = EXCLUDED.needs_hybrid,
                text_char_count = EXCLUDED.text_char_count,
                markdown = EXCLUDED.markdown,
                parse_warnings = EXCLUDED.parse_warnings,
                updated_at = NOW()
            RETURNING id;
            """,
            (
                parsed.source_path,
                content_hash,
                meta.broker_key,
                meta.broker_name,
                meta.title,
                meta.published_date,
                meta.target_ticker,
                meta.category_key,
                meta.main_theme,
                parsed.page_count,
                parsed.parse_mode,
                parser_version,
                meta.parse_status,
                meta.needs_hybrid,
                parsed.text_char_count,
                parsed.markdown,
                json.dumps(parsed.warnings, ensure_ascii=False),
            ),
        )
        return cur.fetchone()[0]


def delete_document_chunks(conn: Any, document_id: int) -> None:
    """재적재 전 기존 document_chunks를 삭제한다 (commit 안 함).

    documents FK가 ON DELETE CASCADE지만, 문서는 유지하고 청크만 교체하는
    재청킹 경로를 위해 명시적으로 청크만 삭제한다.
    트랜잭션 경계는 호출자(pdf_ingest)가 제어한다 — 여기서 conn.commit()을 호출하지 않는다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM document_chunks WHERE document_id = %s;",
            (document_id,),
        )


def persist_document_chunks(
    conn: Any,
    *,
    document_id: int,
    source_date: date,
    broker_key: str | None,
    category_key: str | None,
    main_theme: str | None,
    drafts: list[PdfChunkDraft],
) -> int:
    """PdfChunkDraft들을 document_chunks에 INSERT한다 (embed_status='pending', embedding NULL).

    executemany 배치 적재. 삽입 행 수 반환. 빈 drafts는 0 반환. commit 안 함.
    ticker_tags는 jsonb로 직렬화. 임베딩은 패스2(upsert_embeddings)에서 채운다.
    트랜잭션 경계는 호출자(pdf_ingest)가 제어한다 — 여기서 conn.commit()을 호출하지 않는다.
    """
    if not drafts:
        return 0

    query = """
    INSERT INTO document_chunks (
        document_id,
        source_date,
        broker_key,
        section_path,
        chunk_seq,
        is_table,
        category_key,
        main_theme,
        ticker_tags,
        canonical_summary,
        content_clean,
        embed_payload,
        priority_score
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
    );
    """

    params: list[tuple[Any, ...]] = []
    for draft in drafts:
        # 표는 정보 밀도가 높아 산문보다 우선순위를 살짝 높인다.
        priority_score = 1.2 if draft.is_table else 1.0
        params.append(
            (
                document_id,
                source_date,
                broker_key,
                draft.section_path,
                draft.chunk_seq,
                draft.is_table,
                category_key,
                main_theme,
                json.dumps(draft.ticker_tags, ensure_ascii=False),
                draft.canonical_summary,
                draft.content_clean,
                draft.embed_payload,
                priority_score,
            )
        )

    with conn.cursor() as cur:
        cur.executemany(query, params)

    return len(params)


def load_pending_document_chunks(
    conn: Any,
    *,
    document_id: int | None = None,
    include_failed: bool = True,
) -> list[tuple[int, str]]:
    """임베딩이 필요한 청크 (id, embed_payload)를 조회한다.

    embed_status='pending' (include_failed=True면 'failed'도) 인 행.
    document_id 지정 시 해당 문서로 한정, None이면 전체(backfill용).
    검색은 embed_status='done'만 보므로 pending/failed가 패스2 대상이다.
    commit은 호출자 책임(이 함수는 조회만, 트랜잭션 경계 제어 안 함).
    """
    statuses = ("pending", "failed") if include_failed else ("pending",)
    placeholders = ", ".join(["%s"] * len(statuses))
    conditions = [f"embed_status IN ({placeholders})"]
    params: list[Any] = list(statuses)

    if document_id is not None:
        conditions.append("document_id = %s")
        params.append(document_id)

    query = f"""
    SELECT id, embed_payload
    FROM document_chunks
    WHERE {" AND ".join(conditions)}
    ORDER BY id;
    """

    with conn.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

    return [(row[0], row[1]) for row in rows]


def search_document_chunks(
    conn: Any,
    query_vec: list[float],
    *,
    category_filter: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """벡터 유사도 검색. 문서당 최고 점수 청크 1개만 반환(per-document dedup).

    같은 문서에서 여러 청크가 높은 점수를 받아도 top-1만 노출한다. 투자의견 이력
    테이블처럼 동일 문서 내 반복 패턴이 검색 결과를 독점하는 문제를 방지한다.

    category_filter: 지정 시 해당 카테고리 문서만 검색(T16 cross-link 시 활용).
    query_vec: 1536차원 OpenAI text-embedding-3-small 벡터.
    """
    vec_lit = "[" + ",".join(repr(float(x)) for x in query_vec) + "]"
    cat_clause = "AND d.category_key = %(category)s" if category_filter else ""
    params: dict[str, Any] = {"category": category_filter}

    sql = f"""
    WITH ranked AS (
        SELECT
            dc.id,
            dc.document_id,
            dc.chunk_seq,
            dc.is_table,
            dc.section_path,
            dc.content_clean,
            dc.category_key,
            dc.main_theme,
            dc.ticker_tags,
            d.title            AS doc_title,
            d.source_path,
            d.broker_key,
            d.published_date,
            1 - (dc.embedding <=> '{vec_lit}'::vector) AS similarity,
            ROW_NUMBER() OVER (
                PARTITION BY dc.document_id
                ORDER BY dc.embedding <=> '{vec_lit}'::vector
            ) AS rn
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.embed_status = 'done'
          {cat_clause}
    )
    SELECT
        id, document_id, chunk_seq, is_table, section_path,
        content_clean, category_key, main_theme, ticker_tags,
        doc_title, source_path, broker_key, published_date, similarity
    FROM ranked
    WHERE rn = 1
    ORDER BY similarity DESC
    LIMIT %(top_k)s;
    """
    params["top_k"] = top_k

    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [desc.name for desc in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
