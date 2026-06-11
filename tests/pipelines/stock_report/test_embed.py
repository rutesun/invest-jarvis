from __future__ import annotations

from typing import Any

import pytest

from src.pipelines.stock_report.embed import (
    EMBED_DIM,
    _format_vector_literal,
    embed_payloads,
    upsert_embeddings,
)


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


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


class FakeEmbeddings:
    """langchain_openai.OpenAIEmbeddings 대체 — 호출 텍스트/배치를 기록한다."""

    calls: list[list[str]] = []
    last_kwargs: dict[str, Any] = {}
    dim: int = EMBED_DIM

    def __init__(self, model: str = "fake", **kwargs: Any) -> None:
        self.model = model
        FakeEmbeddings.last_kwargs = {"model": model, **kwargs}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        FakeEmbeddings.calls.append(list(texts))
        # 각 payload 길이를 시드로 써서 결정적·순서 식별 가능한 벡터를 만든다.
        return [[float(len(text))] * FakeEmbeddings.dim for text in texts]


@pytest.fixture(autouse=True)
def _reset_fake_embeddings() -> None:
    FakeEmbeddings.calls = []
    FakeEmbeddings.last_kwargs = {}
    FakeEmbeddings.dim = EMBED_DIM


def test_embed_payloads_batches_and_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)

    payloads = ["a", "bb", "ccc", "dddd", "eeeee"]
    vectors = embed_payloads(payloads, batch_size=2)

    # batch_size=2 → 3개 배치(2,2,1)로 끊겨야 한다.
    assert len(FakeEmbeddings.calls) == 3
    assert FakeEmbeddings.calls[0] == ["a", "bb"]
    assert FakeEmbeddings.calls[1] == ["ccc", "dddd"]
    assert FakeEmbeddings.calls[2] == ["eeeee"]

    # 입력 순서 보존: 각 벡터 첫 성분 = 해당 payload 길이.
    assert len(vectors) == 5
    assert [vec[0] for vec in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert all(len(vec) == EMBED_DIM for vec in vectors)


def test_embed_payloads_dimension_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeEmbeddings.dim = 3  # 기대 차원(EMBED_DIM)과 다른 잘못된 차원
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)

    with pytest.raises(ValueError, match="임베딩 차원 불일치"):
        embed_payloads(["payload"])


def test_embed_payloads_empty_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)

    vectors = embed_payloads([])

    assert vectors == []
    assert FakeEmbeddings.calls == []


def test_upsert_embeddings_rejects_unknown_table() -> None:
    conn = FakeConnection()
    with pytest.raises(ValueError, match="허용되지 않은 임베딩 대상 테이블"):
        upsert_embeddings(
            conn,
            table="evil_table",
            rows=[(1, [0.0] * EMBED_DIM)],
        )


def test_upsert_embeddings_updates_done_status() -> None:
    conn = FakeConnection()
    rows = [(1, [0.1] * EMBED_DIM), (2, [0.2] * EMBED_DIM)]

    count = upsert_embeddings(conn, table="document_chunks", rows=rows)

    assert count == 2
    assert len(conn.executemany_calls) == 1
    query, params = conn.executemany_calls[0]
    assert "document_chunks" in query
    assert "embed_status = 'done'" in query
    assert "%s::vector" in query
    assert "embed_attempts = embed_attempts + 1" in query
    # params: (vec_literal, model, version, chunk_id)
    assert len(params) == 2
    vec_literal, model, version, chunk_id = params[0]
    assert vec_literal.startswith("[")
    assert chunk_id == 1
    assert params[1][3] == 2
    # 호출자가 트랜잭션을 제어한다 — 적재 함수는 commit하지 않는다.
    assert conn.commits == 0


def test_upsert_embeddings_empty_returns_zero() -> None:
    conn = FakeConnection()
    count = upsert_embeddings(conn, table="document_chunks", rows=[])
    assert count == 0
    assert conn.executemany_calls == []


def test_upsert_embeddings_dimension_guard() -> None:
    conn = FakeConnection()
    with pytest.raises(ValueError, match="임베딩 차원 불일치"):
        upsert_embeddings(
            conn,
            table="document_chunks",
            rows=[(1, [0.1, 0.2, 0.3])],  # EMBED_DIM과 다른 길이
        )


def test_format_vector_literal() -> None:
    assert _format_vector_literal([1.0, 2.0]) == "[1.0,2.0]"
    assert _format_vector_literal([]) == "[]"
    # int 입력도 float로 정규화된다.
    assert _format_vector_literal([1, 2, 3]) == "[1.0,2.0,3.0]"


def test_embed_payloads_truncates_over_token_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)

    long_text = "가" * 20000  # 토큰 한도를 크게 초과하는 거대 표 시뮬레이션
    embed_payloads([long_text], max_tokens=10)

    # 임베딩에 실제로 넘어간 텍스트는 토큰 상한으로 잘려 원본보다 짧다.
    sent = FakeEmbeddings.calls[0][0]
    assert len(sent) < len(long_text)


def test_embed_payloads_uses_embed_specific_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setenv("STOCK_REPORT_EMBED_API_KEY", "sk-embed-test")
    monkeypatch.setenv("STOCK_REPORT_EMBED_BASE_URL", "https://emb.example.com/v1")

    embed_payloads(["x"])

    assert FakeEmbeddings.last_kwargs.get("api_key") == "sk-embed-test"
    assert FakeEmbeddings.last_kwargs.get("base_url") == "https://emb.example.com/v1"


def test_embed_payloads_ignores_gateway_base_url_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.delenv("STOCK_REPORT_EMBED_BASE_URL", raising=False)
    monkeypatch.delenv("STOCK_REPORT_EMBED_API_KEY", raising=False)
    # chat용 사내 게이트웨이가 환경에 있어도 임베딩은 OpenAI 공식 기본을 쓴다.
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.internal/v1")

    embed_payloads(["x"])

    assert FakeEmbeddings.last_kwargs.get("base_url") == "https://api.openai.com/v1"


def test_embed_payloads_reads_open_ai_embedding_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.delenv("STOCK_REPORT_EMBED_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_AI_EMBEDDING_KEY", "sk-embedding-slot")

    embed_payloads(["x"])

    # 게이트웨이 chat 키와 분리된 OpenAI 직접 임베딩 키 슬롯을 인식한다.
    assert FakeEmbeddings.last_kwargs.get("api_key") == "sk-embedding-slot"
