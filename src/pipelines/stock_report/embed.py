"""OpenAI 임베딩 + pgvector upsert (T11/T15 공용).

knowledge_chunks(텔레그램)와 document_chunks(PDF)가 같은 임베딩 모델/payload 형식을
쓰므로 같은 벡터 좌표계에 있다(UNION ALL 검색 성립). 이 모듈은 두 테이블 공용이며
대상 테이블은 ``table`` 파라미터로 받는다.

2-패스 원칙(Codex #4): OpenAI 호출(embed_payloads)과 DB 적재(upsert_embeddings)를
분리해 외부 API를 트랜잭션 밖에 둔다.
"""

from __future__ import annotations

import os
from typing import Any


EMBED_MODEL = os.getenv("STOCK_REPORT_EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = int(os.getenv("STOCK_REPORT_EMBED_DIM", "1536"))
EMBED_VERSION = os.getenv("STOCK_REPORT_EMBED_VERSION", "v1")
EMBED_BATCH_SIZE = int(os.getenv("STOCK_REPORT_EMBED_BATCH_SIZE", "128"))

_ALLOWED_EMBED_TABLES = frozenset({"knowledge_chunks", "document_chunks"})


def embed_payloads(
    payloads: list[str],
    *,
    model: str = EMBED_MODEL,
    dim: int = EMBED_DIM,
    batch_size: int = EMBED_BATCH_SIZE,
) -> list[list[float]]:
    """payload 텍스트들을 OpenAI 임베딩 벡터로 변환한다 (입력 순서 보존).

    - langchain_openai.OpenAIEmbeddings 사용. batch_size 단위로 끊어 호출.
    - 반환 각 벡터 길이가 dim과 다르면 ValueError(한국어). (차원 가드)
    - 빈 입력은 빈 리스트 반환.
    - import 가드: langchain_openai 미설치 시 한국어 RuntimeError (db._load_psycopg 패턴).
    """
    if not payloads:
        return []

    try:
        from langchain_openai import OpenAIEmbeddings  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency/runtime guard
        raise RuntimeError(
            "langchain-openai가 설치되지 않았습니다. `uv sync` 후 다시 실행하세요."
        ) from exc

    embeddings = OpenAIEmbeddings(model=model)

    vectors: list[list[float]] = []
    for start in range(0, len(payloads), batch_size):
        batch = payloads[start : start + batch_size]
        batch_vectors = embeddings.embed_documents(batch)
        for vec in batch_vectors:
            if len(vec) != dim:
                raise ValueError(f"임베딩 차원 불일치: 기대 {dim}, 실제 {len(vec)} (모델 {model})")
            vectors.append(list(vec))

    return vectors


def upsert_embeddings(
    conn: Any,
    *,
    table: str,
    rows: list[tuple[int, list[float]]],
    model: str = EMBED_MODEL,
    version: str = EMBED_VERSION,
) -> int:
    """청크 id별 임베딩 벡터를 대상 테이블에 적재한다 (embed_status='done').

    rows: [(chunk_id, vector), ...]. table은 화이트리스트 검증.
    각 벡터 길이를 EMBED_DIM과 대조(방어적 차원 가드). commit은 호출자 책임.
    적재한 행 수 반환. 빈 rows는 0 반환.

    2-패스 원칙: OpenAI 호출은 embed_payloads에서 끝나므로 이 함수는 순수 DB 적재다.
    트랜잭션 경계는 호출자(pdf_ingest)가 제어한다 — 여기서 conn.commit()을 호출하지
    않는다(텔레그램 경로의 persist_classified_chunks가 자체 commit하는 것과 의도적
    차이: PDF는 문서 단위 원자적 트랜잭션 + 2-패스가 요구사항).
    """
    if table not in _ALLOWED_EMBED_TABLES:
        raise ValueError(f"허용되지 않은 임베딩 대상 테이블: {table}")

    if not rows:
        return 0

    params: list[tuple[Any, ...]] = []
    for chunk_id, vector in rows:
        if len(vector) != EMBED_DIM:
            raise ValueError(
                f"임베딩 차원 불일치: 기대 {EMBED_DIM}, 실제 {len(vector)} (chunk_id {chunk_id})"
            )
        params.append((_format_vector_literal(vector), model, version, chunk_id))

    # table은 화이트리스트 검증을 통과한 식별자다(값이 아니라 파라미터 바인딩 불가).
    query = f"""
    UPDATE {table}
       SET embedding = %s::vector,
           embed_model = %s,
           embed_version = %s,
           embed_status = 'done',
           embed_attempts = embed_attempts + 1
     WHERE id = %s;
    """

    with conn.cursor() as cur:
        cur.executemany(query, params)

    return len(params)


def _format_vector_literal(vec: list[float]) -> str:
    """pgvector 입력용 문자열 리터럴. 예: [0.1,0.2,0.3]

    psycopg는 list[float]를 vector로 직접 바인딩하지 못한다(pgvector-python 미설치).
    문자열 리터럴을 만들어 ``%s::vector``로 캐스팅한다.
    """
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
