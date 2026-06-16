"""OpenAI 임베딩 + pgvector upsert (T11/T15 공용).

knowledge_chunks(텔레그램)와 document_chunks(PDF)가 같은 임베딩 모델/payload 형식을
쓰므로 같은 벡터 좌표계에 있다(UNION ALL 검색 성립). 이 모듈은 두 테이블 공용이며
대상 테이블은 ``table`` 파라미터로 받는다.

2-패스 원칙(Codex #4): OpenAI 호출(embed_payloads)과 DB 적재(upsert_embeddings)를
분리해 외부 API를 트랜잭션 밖에 둔다.

인증/엔드포인트 분리: chat(classify/synthesis)은 사내 게이트웨이(``OPENAI_BASE_URL``)를
경유하지만, 게이트웨이가 임베딩 provider를 막는 경우가 있어 임베딩은 별도 키/URL로
분리한다. 키는 ``STOCK_REPORT_EMBED_API_KEY`` 또는 ``OPEN_AI_EMBEDDING_KEY``로,
엔드포인트는 ``STOCK_REPORT_EMBED_BASE_URL``로 지정한다. base_url 기본은 OpenAI 공식
엔드포인트다(게이트웨이 ``OPENAI_BASE_URL``을 임베딩에 그대로 쓰지 않는다).
"""

from __future__ import annotations

import logging
import os
from typing import Any


logger = logging.getLogger(__name__)

EMBED_MODEL = os.getenv("STOCK_REPORT_EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = int(os.getenv("STOCK_REPORT_EMBED_DIM", "1536"))
EMBED_VERSION = os.getenv("STOCK_REPORT_EMBED_VERSION", "v1")
EMBED_BATCH_SIZE = int(os.getenv("STOCK_REPORT_EMBED_BATCH_SIZE", "128"))
# 임베딩 입력 토큰 상한. text-embedding-3 계열은 8191 토큰 한도라 여유를 둬 8000.
# 한도를 넘는 payload(예: 통째로 담은 거대 표)는 임베딩 전에 잘라 API 실패를 막는다.
EMBED_MAX_TOKENS = int(os.getenv("STOCK_REPORT_EMBED_MAX_TOKENS", "8000"))

# 임베딩 기본 엔드포인트(OpenAI 공식). 사내 게이트웨이는 임베딩 provider를 막을 수
# 있어, STOCK_REPORT_EMBED_BASE_URL로 명시하지 않는 한 게이트웨이 OPENAI_BASE_URL을
# 임베딩에 쓰지 않는다.
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

_ALLOWED_EMBED_TABLES = frozenset({"knowledge_chunks", "document_chunks"})


def _resolve_embed_auth() -> tuple[str | None, str]:
    """임베딩 전용 (api_key, base_url)을 환경에서 해석한다.

    - api_key: ``STOCK_REPORT_EMBED_API_KEY`` → ``OPEN_AI_EMBEDDING_KEY`` →
      ``OPENAI_API_KEY`` 순. (``OPEN_AI_EMBEDDING_KEY``는 게이트웨이 chat 키와 분리된
      OpenAI 직접 임베딩 키 슬롯이다.)
    - base_url: ``STOCK_REPORT_EMBED_BASE_URL`` 우선, 없으면 OpenAI 공식.
    함수 내부에서 ``os.getenv``를 읽어 런타임 환경(테스트 setenv 포함)을 반영한다.
    """
    api_key = (
        os.getenv("STOCK_REPORT_EMBED_API_KEY")
        or os.getenv("OPEN_AI_EMBEDDING_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    base_url = os.getenv("STOCK_REPORT_EMBED_BASE_URL") or _DEFAULT_OPENAI_BASE_URL
    return api_key, base_url


def has_embed_auth() -> bool:
    """임베딩 전용 API 키가 해석되는지(존재) 여부.

    키가 없으면 OpenAI 임베딩 호출이 인증 실패하므로, 호출 전에 이 함수로 조기
    skip해 매 호출 인증 실패 경고를 막는다(검색 경로 graceful degradation).
    """
    return _resolve_embed_auth()[0] is not None


def _get_encoding(model: str) -> Any:
    """모델에 맞는 tiktoken 인코딩(미지원 모델은 cl100k_base 폴백)."""
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _truncate_to_tokens(text: str, max_tokens: int, encoding: Any) -> str:
    """text를 max_tokens 이하로 자른다(토큰 경계 기준)."""
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoding.decode(tokens[:max_tokens])


def embed_payloads(
    payloads: list[str],
    *,
    model: str = EMBED_MODEL,
    dim: int = EMBED_DIM,
    batch_size: int = EMBED_BATCH_SIZE,
    max_tokens: int = EMBED_MAX_TOKENS,
) -> list[list[float]]:
    """payload 텍스트들을 OpenAI 임베딩 벡터로 변환한다 (입력 순서 보존).

    - 임베딩 전용 키/base_url(``_resolve_embed_auth``)로 OpenAIEmbeddings를 만든다.
    - ``max_tokens``를 넘는 payload는 토큰 단위로 잘라 임베딩한다(거대 표 토큰 초과 방어).
    - ``batch_size`` 단위로 끊어 호출. 반환 각 벡터 길이가 ``dim``과 다르면 ValueError.
    - 빈 입력은 빈 리스트. langchain_openai 미설치 시 한국어 RuntimeError.
    """
    if not payloads:
        return []

    try:
        from langchain_openai import OpenAIEmbeddings  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency/runtime guard
        raise RuntimeError(
            "langchain-openai가 설치되지 않았습니다. `uv sync` 후 다시 실행하세요."
        ) from exc

    encoding = _get_encoding(model)
    prepared: list[str] = []
    truncated = 0
    for payload in payloads:
        capped = _truncate_to_tokens(payload, max_tokens, encoding)
        if capped != payload:
            truncated += 1
        prepared.append(capped)
    if truncated:
        logger.warning(
            "임베딩 토큰 상한(%d) 초과로 payload %d개를 truncate했다", max_tokens, truncated
        )

    api_key, base_url = _resolve_embed_auth()
    emb_kwargs: dict[str, Any] = {"model": model, "base_url": base_url}
    if api_key:
        emb_kwargs["api_key"] = api_key
    embeddings = OpenAIEmbeddings(**emb_kwargs)

    vectors: list[list[float]] = []
    for start in range(0, len(prepared), batch_size):
        batch = prepared[start : start + batch_size]
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
