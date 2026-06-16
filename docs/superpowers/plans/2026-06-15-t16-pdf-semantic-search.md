# T16 PDF Semantic Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDF `document_chunks`를 텍스트 쿼리로 의미검색하는 재사용 함수 `search_documents`를 만들어, T17 synthesis LLM 툴이 그대로 호출하게 한다.

**Architecture:** 레이어 분리 유지 — SQL은 `db.py`(`search_document_chunks`에 `ticker_filter` 추가), 오케스트레이션은 `retrieval.py`(`search_documents`: 쿼리 임베딩 → 벡터검색 → `DocumentSearchHit` 매핑). 임베딩/검색은 seam으로 주입해 네트워크·DB 없이 테스트. 순환 import는 함수 내부 지연 import로 회피.

**Tech Stack:** Python 3.12, psycopg(Postgres+pgvector), `text-embedding-3-small`(1536d), pytest, uv, ruff.

**관련 스펙:** `docs/superpowers/specs/2026-06-15-t16-telegram-pdf-cross-link-design.md`

**스펙 대비 변경점(계획 중 발견):** 키 부재 가드를 위해 `embed.py`에 공개 헬퍼 `has_embed_auth()`를 추가한다(스펙의 "embed 모듈 인증 해석 재사용"의 구체화). 따라서 변경 파일에 `embed.py`/`test_embed.py`가 포함된다.

**커밋/푸시 주의:** pre-commit의 `check-features-doc`는 경고만 출력(차단 안 함)하므로 Task별 개별 커밋 가능. 단 **push 전**(별도 사용자 승인) 브랜치에 `docs/FEATURES.md` 변경(Task 4)이 있어야 pre-push LLM 게이트를 통과한다.

---

## File Structure

| 파일 | 책임 | Task |
|---|---|---|
| `src/pipelines/stock_report/db.py` | `search_document_chunks`에 `ticker_filter`(exact 태그) 추가 | 1 |
| `src/pipelines/stock_report/embed.py` | `has_embed_auth()` 키 존재 헬퍼 | 2 |
| `src/pipelines/stock_report/retrieval.py` | `DocumentSearchHit` + `search_documents` 검색 래퍼 | 3 |
| `docs/FEATURES.md` | 5-2 PDF Ingest 섹션 검색 항목 갱신 | 4 |
| `tests/pipelines/stock_report/test_db.py` | `ticker_filter` SQL 테스트(append) | 1 |
| `tests/pipelines/stock_report/test_embed.py` | `has_embed_auth` 테스트(append) | 2 |
| `tests/pipelines/stock_report/test_retrieval.py` | `search_documents` 테스트(append, 기존 보존) | 3 |

---

### Task 1: `search_document_chunks`에 `ticker_filter` 추가

**Files:**
- Modify: `src/pipelines/stock_report/db.py:572-631`
- Test: `tests/pipelines/stock_report/test_db.py` (파일 끝에 append)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pipelines/stock_report/test_db.py` 맨 끝에 추가 (기존 `_search_conn`/`_SEARCH_COLS`/`json` 재사용):

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_db.py -k ticker -v`
Expected: FAIL — `TypeError: search_document_chunks() got an unexpected keyword argument 'ticker_filter'`

- [ ] **Step 3: 최소 구현**

`src/pipelines/stock_report/db.py`의 `search_document_chunks` 시그니처에 `ticker_filter`를 추가:

```python
def search_document_chunks(
    conn: Any,
    query_vec: list[float],
    *,
    category_filter: str | None = None,
    ticker_filter: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
```

docstring에 한 줄 추가(`category_filter:` 설명 아래):

```python
    ticker_filter: 지정 시 ticker_tags @> [ticker] (GIN 인덱스) exact 태그 필터. category와 AND.
```

`vec_lit`/`cat_clause`/`params` 블록 바로 아래에 `ticker_clause`를 추가:

```python
    vec_lit = "[" + ",".join(repr(float(x)) for x in query_vec) + "]"
    cat_clause = "AND d.category_key = %(category)s" if category_filter else ""
    params: dict[str, Any] = {"category": category_filter}

    ticker_clause = ""
    if ticker_filter:
        ticker_clause = "AND dc.ticker_tags @> %(ticker)s::jsonb"
        params["ticker"] = json.dumps([ticker_filter])
```

SQL의 `WHERE` 절에서 `{cat_clause}` 다음 줄에 `{ticker_clause}`를 넣는다:

```python
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.embed_status = 'done'
          {cat_clause}
          {ticker_clause}
    )
```

(`json`은 `db.py` 상단에 이미 import돼 있다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_db.py -v`
Expected: PASS (신규 3개 + 기존 search 테스트 4개 포함 전부 통과)

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/stock_report/db.py tests/pipelines/stock_report/test_db.py
git commit -m "$(cat <<'EOF'
feat(t16): add ticker_filter to search_document_chunks

ticker_tags @> [ticker] exact-tag filter via GIN index, AND-combined with
category_filter. Enables ticker-scoped PDF search for the T16 search wrapper.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `embed.py`에 `has_embed_auth()` 헬퍼

**Files:**
- Modify: `src/pipelines/stock_report/embed.py` (`_resolve_embed_auth` 정의 바로 아래)
- Test: `tests/pipelines/stock_report/test_embed.py` (import 한 줄 + 파일 끝 append)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pipelines/stock_report/test_embed.py` 상단 import 블록(`from src.pipelines.stock_report.embed import (` ... `)`)에 `has_embed_auth`를 알파벳 순서에 맞게 추가한다. 그리고 파일 끝에 추가:

```python
def test_has_embed_auth_true_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_REPORT_EMBED_API_KEY", "sk-embed-test")
    assert has_embed_auth() is True


def test_has_embed_auth_false_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("STOCK_REPORT_EMBED_API_KEY", "OPEN_AI_EMBEDDING_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert has_embed_auth() is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_embed.py -k has_embed_auth -v`
Expected: FAIL — `ImportError: cannot import name 'has_embed_auth'`

- [ ] **Step 3: 최소 구현**

`src/pipelines/stock_report/embed.py`의 `_resolve_embed_auth()` 함수 정의 바로 아래에 추가:

```python
def has_embed_auth() -> bool:
    """임베딩 전용 API 키가 해석되는지(존재) 여부.

    키가 없으면 OpenAI 임베딩 호출이 인증 실패하므로, 호출 전에 이 함수로 조기
    skip해 매 호출 인증 실패 경고를 막는다(검색 경로 graceful degradation).
    """
    return _resolve_embed_auth()[0] is not None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_embed.py -v`
Expected: PASS (신규 2개 + 기존 전부)

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/stock_report/embed.py tests/pipelines/stock_report/test_embed.py
git commit -m "$(cat <<'EOF'
feat(t16): add has_embed_auth() embed-key presence helper

Lets the search path skip embedding calls when no embed key is configured,
avoiding a per-call auth-failure warning. Reuses _resolve_embed_auth.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `DocumentSearchHit` + `search_documents` (retrieval.py)

**Files:**
- Modify: `src/pipelines/stock_report/retrieval.py` (상단 import + 파일 끝 append)
- Test: `tests/pipelines/stock_report/test_retrieval.py` (import 블록 + 파일 끝 append, 기존 보존)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pipelines/stock_report/test_retrieval.py` 상단 import를 아래로 교체(`pytest` 추가, retrieval import에 `DocumentSearchHit`/`search_documents` 추가):

```python
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.pipelines.stock_report.retrieval import (
    DocumentSearchHit,
    SameDayChunk,
    build_same_day_bundle,
    load_same_day_chunks,
    search_documents,
)
```

파일 **맨 끝**에 추가:

```python
# --- search_documents (T16 PDF semantic search) ----------------------------


def _doc_row(chunk_id: int = 1, *, similarity: float = 0.87) -> dict[str, Any]:
    return {
        "id": chunk_id,
        "document_id": 10,
        "chunk_seq": 3,
        "is_table": False,
        "section_path": "intro",
        "content_clean": "HBM 관련 본문",
        "category_key": "반도체",
        "main_theme": "HBM",
        "ticker_tags": ["000660.KS"],
        "doc_title": "소부장 리포트",
        "source_path": "data/files/doc.pdf",
        "broker_key": "shinhan",
        "published_date": date(2026, 6, 2),
        "similarity": similarity,
    }


class _RecordingEmbed:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, payloads: list[str]) -> list[list[float]]:
        self.calls.append(payloads)
        return [[0.0] * 1536 for _ in payloads]


class _RecordingSearch:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        conn: Any,
        query_vec: list[float],
        *,
        category_filter: str | None = None,
        ticker_filter: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "category_filter": category_filter,
                "ticker_filter": ticker_filter,
                "top_k": top_k,
                "vec_len": len(query_vec),
            }
        )
        return self.rows


def test_search_documents_embeds_query_once_and_maps_hits() -> None:
    embed = _RecordingEmbed()
    search = _RecordingSearch([_doc_row(1)])

    hits = search_documents(
        None,
        "HBM 메모리 수요",
        category="반도체",
        ticker="000660.KS",
        top_k=3,
        embed_fn=embed,
        search_fn=search,
    )

    assert embed.calls == [["HBM 메모리 수요"]]
    assert search.calls == [
        {"category_filter": "반도체", "ticker_filter": "000660.KS", "top_k": 3, "vec_len": 1536}
    ]
    assert len(hits) == 1
    assert isinstance(hits[0], DocumentSearchHit)
    assert hits[0].chunk_id == 1
    assert hits[0].doc_title == "소부장 리포트"
    assert hits[0].similarity == 0.87
    assert hits[0].ticker_tags == ["000660.KS"]


def test_search_documents_blank_query_returns_empty_without_calls() -> None:
    embed = _RecordingEmbed()
    search = _RecordingSearch([_doc_row()])

    assert search_documents(None, "   ", embed_fn=embed, search_fn=search) == []
    assert embed.calls == []
    assert search.calls == []


def test_search_documents_embed_failure_returns_empty() -> None:
    def boom(_payloads: list[str]) -> list[list[float]]:
        raise RuntimeError("embed down")

    search = _RecordingSearch([_doc_row()])
    hits = search_documents(None, "HBM", embed_fn=boom, search_fn=search)

    assert hits == []
    assert search.calls == []


def test_search_documents_no_embed_key_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("STOCK_REPORT_EMBED_API_KEY", "OPEN_AI_EMBEDDING_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    search = _RecordingSearch([_doc_row()])

    # embed_fn 미주입 → 실제 경로 → has_embed_auth False → 검색 호출 없이 빈 리스트.
    hits = search_documents(None, "HBM", search_fn=search)

    assert hits == []
    assert search.calls == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_retrieval.py -k search_documents -v`
Expected: FAIL — `ImportError: cannot import name 'DocumentSearchHit'`

- [ ] **Step 3: 최소 구현 — import 추가**

`src/pipelines/stock_report/retrieval.py` 상단 import 블록을 아래로 교체:

```python
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.pipelines.stock_report.chunking import KNOWLEDGE_CHUNK_SOURCE_TYPE

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: 최소 구현 — 함수/타입 추가**

`src/pipelines/stock_report/retrieval.py` **맨 끝**(`load_same_day_bundle` 아래)에 추가:

```python
@dataclass(slots=True)
class DocumentSearchHit:
    chunk_id: int
    document_id: int
    doc_title: str | None
    broker_key: str | None
    published_date: date | None
    section_path: str
    is_table: bool
    content_clean: str
    category_key: str | None
    main_theme: str | None
    ticker_tags: list[str]
    similarity: float


def _to_document_search_hit(row: dict[str, Any]) -> DocumentSearchHit:
    return DocumentSearchHit(
        chunk_id=row["id"],
        document_id=row["document_id"],
        doc_title=row.get("doc_title"),
        broker_key=row.get("broker_key"),
        published_date=row.get("published_date"),
        section_path=row["section_path"],
        is_table=row["is_table"],
        content_clean=row["content_clean"],
        category_key=row.get("category_key"),
        main_theme=row.get("main_theme"),
        ticker_tags=row.get("ticker_tags") or [],
        similarity=row["similarity"],
    )


def search_documents(
    conn: Any,
    query_text: str,
    *,
    category: str | None = None,
    ticker: str | None = None,
    top_k: int = 5,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[DocumentSearchHit]:
    """PDF document_chunks 의미검색. query_text를 임베딩해 벡터검색하고 hit 리스트 반환.

    T17 synthesis LLM 툴이 그대로 감싸 쓰는 검색 함수. category/ticker는 exact 필터,
    의미 랭킹은 벡터. 모든 실패는 graceful(빈 리스트) — 호출 경로를 깨지 않는다.

    embed_fn/search_fn은 테스트 주입용 seam(기본 None → 실제 구현을 함수 내부에서
    지연 import). 지연 import는 순환(retrieval→db→synthesize→retrieval) 회피용이며
    기존 관례(_load_psycopg 등)와 동일하다.
    """
    if not query_text or not query_text.strip():
        return []

    if embed_fn is None:
        from src.pipelines.stock_report.embed import embed_payloads, has_embed_auth

        if not has_embed_auth():
            logger.info("임베딩 키 미설정 → PDF 검색 skip (query=%.40s)", query_text)
            return []
        embed_fn = embed_payloads
    if search_fn is None:
        from src.pipelines.stock_report.db import search_document_chunks

        search_fn = search_document_chunks

    try:
        vectors = embed_fn([query_text])
        if not vectors:
            return []
        rows = search_fn(
            conn,
            vectors[0],
            category_filter=category,
            ticker_filter=ticker,
            top_k=top_k,
        )
    except Exception:
        logger.warning("PDF 검색 실패 (query=%.40s)", query_text, exc_info=True)
        return []

    return [_to_document_search_hit(row) for row in rows]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_retrieval.py -v`
Expected: PASS (신규 4개 + 기존 번들 테스트 전부)

- [ ] **Step 6: 커밋**

```bash
git add src/pipelines/stock_report/retrieval.py tests/pipelines/stock_report/test_retrieval.py
git commit -m "$(cat <<'EOF'
feat(t16): add search_documents PDF semantic-search wrapper

Embeds a text query then calls search_document_chunks (category/ticker filter,
per-doc dedup), returning DocumentSearchHit list. Tool-ready for T17 LLM
function calling. Seam-injected embed_fn/search_fn (no network/DB in tests);
lazy import avoids retrieval→db→synthesize cycle; all failures degrade to [].

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `docs/FEATURES.md` 갱신

**Files:**
- Modify: `docs/FEATURES.md` (5-2 PDF Ingest 섹션)

- [ ] **Step 1: 검색 항목 갱신**

`docs/FEATURES.md`에서 아래 블록을 찾아 교체:

찾기:
```markdown
**검색 (`search_document_chunks`):**
- CTE + `ROW_NUMBER() OVER (PARTITION BY document_id)` per-document dedup: 동일 문서가 top-K를 독점하지 않도록 문서당 최고 유사도 1개만 반환
- `category_filter`로 카테고리 내 검색 범위 한정 가능
- `similarity` = `1 - (embedding <=> query_vec)` cosine 유사도 반환
```

교체:
```markdown
**검색 (`search_document_chunks` / `search_documents`):**
- CTE + `ROW_NUMBER() OVER (PARTITION BY document_id)` per-document dedup: 동일 문서가 top-K를 독점하지 않도록 문서당 최고 유사도 1개만 반환
- `category_filter`(카테고리)·`ticker_filter`(`ticker_tags @>` exact 태그)로 검색 범위 한정, AND 결합
- `search_documents(query_text, ...)`: 텍스트 쿼리를 임베딩해 검색하는 래퍼(T17 synthesis LLM 툴이 그대로 호출). 임베딩 키 부재/호출 실패 시 graceful 빈 결과
- `similarity` = `1 - (embedding <=> query_vec)` cosine 유사도 반환
```

- [ ] **Step 2: 제약 항목 갱신**

찾기:
```markdown
- Telegram-PDF 통합 retrieval/cross-link(knowledge_chunks ∪ document_chunks)는 후속 작업(T16)
```

교체:
```markdown
- PDF 의미검색(`search_documents`)은 제공하나, synthesis LLM이 이를 툴로 소비해 텔레그램 리포트에 PDF 근거를 넣는 것은 후속 작업(T17)
```

- [ ] **Step 3: 커밋**

```bash
git add docs/FEATURES.md
git commit -m "$(cat <<'EOF'
docs(t16): document PDF semantic search in FEATURES

ticker_filter + search_documents text-query wrapper; cross-link consumption
deferred to T17.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 전체 검증

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest tests/pipelines/stock_report/ -q`
Expected: PASS (회귀 없음). 신규 테스트 9개(Task1 3 + Task2 2 + Task3 4) 포함.

- [ ] **Step 2: 린트/포맷**

Run: `uv run ruff check src/pipelines/stock_report/db.py src/pipelines/stock_report/embed.py src/pipelines/stock_report/retrieval.py tests/pipelines/stock_report/`
Expected: `All checks passed!`

Run: `uv run ruff format --check src/pipelines/stock_report/retrieval.py src/pipelines/stock_report/db.py src/pipelines/stock_report/embed.py`
Expected: 변경 없음 (필요 시 `uv run ruff format <files>` 후 재커밋)

- [ ] **Step 3: import 순환 회귀 가드(수동)**

Run: `uv run python -c "import src.pipelines.stock_report.retrieval as r; print(r.search_documents.__name__)"`
Expected: `search_documents` 출력 (ImportError 없음 = 순환 미발생)

---

## Self-Review (작성자 점검 결과)

**1. Spec coverage:**
- `ticker_filter` → Task 1 ✅
- `search_documents` + `DocumentSearchHit`(chunk_id=row["id"] 매핑) → Task 3 ✅
- 깨끗한 텍스트 쿼리(호출자 책임) → `search_documents`가 `query_text` 그대로 임베딩 ✅
- 임베딩 키 부재 선제 가드 → Task 2 `has_embed_auth` + Task 3 가드 ✅
- 광역 `except Exception` + warning → Task 3 ✅
- 순환 import 지연 import → Task 3 ✅
- graceful(빈 리스트) 에러 처리 → Task 3 (빈 쿼리/예외/키부재/빈결과) ✅
- 테스트 test_retrieval append(기존 보존) + test_db 확장 → Task 1·3 ✅
- FEATURES.md → Task 4 ✅
- 마이그레이션 없음 / `pipeline.py`·`main.py` 미변경 → 계획에 해당 Task 없음(의도) ✅

**2. Placeholder scan:** "TBD"/"적절히 처리" 등 없음. 모든 코드 step은 실제 코드 포함.

**3. Type consistency:** `ticker_filter`(db) ↔ `ticker_filter=ticker`(search_documents 호출) 일치. `search_documents`/`DocumentSearchHit`/`has_embed_auth` 이름이 정의·사용·테스트에서 동일. `DocumentSearchHit` 필드가 `_to_document_search_hit` 매핑 및 `search_document_chunks` 반환 키(`id`,`document_id`,...)와 일치.
