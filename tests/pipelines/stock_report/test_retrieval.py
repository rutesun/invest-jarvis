from __future__ import annotations

from datetime import date
from typing import Any

from src.pipelines.stock_report.retrieval import (
    SameDayChunk,
    build_same_day_bundle,
    load_same_day_chunks,
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
        source_date=source_date,
        channel_key=channel_key,
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
    assert chunks[0].display_category == "AI인프라"
    assert chunks[0].display_theme == "AI 데이터센터"
    query, params = conn.cursor_obj.executed[0]
    assert "WHERE source_date = %s" in query
    assert "source_type = %s" in query
    assert "message_type = ANY" in query
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
