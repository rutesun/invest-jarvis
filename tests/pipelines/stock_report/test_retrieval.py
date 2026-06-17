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


class FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.executed.append((query, params))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeConnection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.cursor_obj = FakeCursor(rows)

    def cursor(self) -> FakeCursor:
        return self.cursor_obj


def _chunk(
    chunk_id: int,
    *,
    source_date: date = date(2026, 5, 26),
    source_pk: int | None = None,
    channel_key: str = "hana_us_stock",
    category_key: str = "반도체",
    main_theme: str | None = "HBM",
    provisional_category: str | None = None,
    provisional_theme: str | None = None,
    ticker_tags: list[str] | None = None,
    canonical_summary: str | None = None,
    priority_score: float = 1.0,
) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=source_pk or chunk_id,
        source_message_db_id=source_pk or chunk_id,
        source_date=source_date,
        channel_key=channel_key,
        channel_name=channel_key,
        channel_message_id=str(source_pk or chunk_id),
        message_type="signal",
        event_type="해석/전망",
        category_key=category_key,
        main_theme=main_theme,
        provisional_category=provisional_category,
        provisional_theme=provisional_theme,
        is_provisional=bool(provisional_category or provisional_theme),
        sub_themes=[],
        ticker_tags=ticker_tags or [],
        theme_tags=[],
        canonical_summary=canonical_summary or f"summary-{chunk_id}",
        supporting_facts=[],
        evidence_items=[],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=priority_score,
    )


def test_load_same_day_chunks_filters_report_date_and_source_type() -> None:
    rows = [
        (
            10,
            "telegram_unit_v2",
            100,
            date(2026, 5, 26),
            "kwusa",
            "키움 미국주식",
            "51014",
            "signal",
            "실적",
            "AI인프라",
            "AI 데이터센터",
            None,
            None,
            False,
            ["전력"],
            ["NVDA"],
            ["AI 데이터센터"],
            "NVDA 데이터센터 수요 강세",
            ["데이터센터 매출 증가"],
            [{"kind": "fact", "text": "데이터센터 매출 증가"}],
            [{"code": "test"}],
            "원문",
            0.9,
        )
    ]
    conn = FakeConnection(rows)

    chunks = load_same_day_chunks(conn, "2026-05-26")

    assert len(chunks) == 1
    assert chunks[0].id == 10
    assert chunks[0].source_message_db_id == 100
    assert chunks[0].display_category == "AI인프라"
    assert chunks[0].display_theme == "AI 데이터센터"
    assert chunks[0].channel_name == "키움 미국주식"
    assert chunks[0].channel_message_id == "51014"
    query, params = conn.cursor_obj.executed[0]
    assert "LEFT JOIN telegram_messages tm ON tm.id = kc.source_pk" in query
    assert "WHERE kc.source_date = %s" in query
    assert "kc.source_type = %s" in query
    assert "kc.message_type = ANY" in query
    assert params == ("2026-05-26", "telegram_unit_v2", ["signal", "data"])


def test_build_same_day_bundle_groups_by_category_theme_and_ticker() -> None:
    chunks = [
        _chunk(1, category_key="반도체", main_theme="HBM", ticker_tags=["NVDA", "삼성전자"]),
        _chunk(2, category_key="반도체", main_theme="AI 반도체", ticker_tags=["NVDA"]),
        _chunk(3, category_key="자동차", main_theme="하이브리드", ticker_tags=["현대차"]),
    ]

    bundle = build_same_day_bundle(date(2026, 5, 26), chunks)

    assert bundle.report_date == date(2026, 5, 26)
    assert [bucket.category_key for bucket in bundle.category_buckets] == ["반도체", "자동차"]
    semiconductor = bundle.category_buckets[0]
    assert [bucket.theme_key for bucket in semiconductor.theme_buckets] == ["HBM", "AI 반도체"]
    assert [bucket.ticker for bucket in semiconductor.ticker_buckets] == ["NVDA", "삼성전자"]
    assert [chunk.id for chunk in semiconductor.ticker_buckets[0].chunks] == [1, 2]
    assert [bucket.ticker for bucket in bundle.focus_ticker_buckets] == [
        "NVDA",
        "삼성전자",
        "현대차",
    ]


def test_build_same_day_bundle_uses_provisional_category_for_unclassified_display() -> None:
    chunks = [
        _chunk(
            1,
            category_key="unclassified",
            main_theme=None,
            provisional_category="운송/물류",
            provisional_theme="연료비/BAF",
            ticker_tags=["현대글로비스"],
        )
    ]

    bundle = build_same_day_bundle(date(2026, 5, 26), chunks)

    assert [bucket.category_key for bucket in bundle.category_buckets] == ["운송/물류"]
    assert bundle.category_buckets[0].is_provisional is True
    assert [bucket.theme_key for bucket in bundle.category_buckets[0].theme_buckets] == [
        "연료비/BAF"
    ]


def test_build_same_day_bundle_dedupes_same_day_duplicate_summaries_without_hard_cap() -> None:
    duplicate = _chunk(
        2,
        source_pk=200,
        category_key="반도체",
        main_theme="HBM",
        ticker_tags=["NVDA"],
        canonical_summary="HBM 수급이 타이트하다",
        priority_score=0.5,
    )
    higher_priority_duplicate = _chunk(
        1,
        source_pk=100,
        category_key="반도체",
        main_theme="HBM",
        ticker_tags=["NVDA"],
        canonical_summary="HBM 수급이 타이트하다",
        priority_score=1.0,
    )
    unique_chunks = [
        _chunk(
            chunk_id,
            category_key="반도체",
            main_theme="HBM",
            ticker_tags=["NVDA"],
            canonical_summary=f"서로 다른 요약 {chunk_id}",
        )
        for chunk_id in range(3, 15)
    ]

    bundle = build_same_day_bundle(
        date(2026, 5, 26),
        [duplicate, higher_priority_duplicate, *unique_chunks],
    )

    semiconductor = bundle.category_buckets[0]
    assert len(semiconductor.chunks) == 13
    assert semiconductor.chunks[0].id == 1
    assert {chunk.id for chunk in semiconductor.chunks} == {1, *range(3, 15)}


def test_build_same_day_bundle_keeps_same_summary_from_different_channels() -> None:
    chunks = [
        _chunk(
            1,
            channel_key="kwusa",
            canonical_summary="HBM 수급이 타이트하다",
            ticker_tags=["NVDA"],
        ),
        _chunk(
            2,
            channel_key="shinhanresearch",
            canonical_summary="HBM 수급이 타이트하다",
            ticker_tags=["NVDA"],
        ),
    ]

    bundle = build_same_day_bundle(date(2026, 5, 26), chunks)

    assert [chunk.id for chunk in bundle.chunks] == [1, 2]


def test_build_same_day_bundle_marks_unclassified_without_overlay_as_low_confidence() -> None:
    chunks = [
        _chunk(
            1,
            category_key="unclassified",
            main_theme=None,
            provisional_category=None,
            provisional_theme=None,
            ticker_tags=[],
        )
    ]

    bundle = build_same_day_bundle(date(2026, 5, 26), chunks)

    assert [chunk.id for chunk in bundle.low_confidence_chunks] == [1]


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
    assert hits[0].source_path == "data/files/doc.pdf"
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

    hits = search_documents(None, "HBM", search_fn=search)

    assert hits == []
    assert search.calls == []


def test_search_documents_embed_returns_empty_list_returns_empty() -> None:
    search = _RecordingSearch([_doc_row()])
    hits = search_documents(None, "HBM", embed_fn=lambda _payloads: [], search_fn=search)
    assert hits == []
    assert search.calls == []


def test_search_documents_search_failure_returns_empty() -> None:
    embed = _RecordingEmbed()

    def boom(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("db down")

    hits = search_documents(None, "HBM", embed_fn=embed, search_fn=boom)
    assert hits == []
    assert embed.calls == [["HBM"]]
