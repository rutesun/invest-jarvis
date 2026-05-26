from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.pipelines.stock_report.chunking import KNOWLEDGE_CHUNK_SOURCE_TYPE


@dataclass(slots=True)
class SameDayChunk:
    id: int
    source_type: str
    source_pk: int | None
    source_date: date
    channel_key: str | None
    message_type: str
    event_type: str | None
    category_key: str
    main_theme: str | None
    provisional_category: str | None
    provisional_theme: str | None
    is_provisional: bool
    sub_themes: list[str]
    ticker_tags: list[str]
    theme_tags: list[str]
    canonical_summary: str
    supporting_facts: list[str]
    evidence_items: list[dict[str, Any]]
    qa_warnings: list[dict[str, Any]]
    content_clean: str
    priority_score: float

    @property
    def display_category(self) -> str:
        if self.category_key == "unclassified" and self.provisional_category:
            return self.provisional_category
        return self.category_key

    @property
    def display_theme(self) -> str | None:
        return self.main_theme or self.provisional_theme


@dataclass(slots=True)
class ThemeBucket:
    theme_key: str
    category_key: str
    chunks: list[SameDayChunk] = field(default_factory=list)
    is_provisional: bool = False


@dataclass(slots=True)
class TickerBucket:
    ticker: str
    chunks: list[SameDayChunk] = field(default_factory=list)


@dataclass(slots=True)
class CategoryBucket:
    category_key: str
    chunks: list[SameDayChunk] = field(default_factory=list)
    theme_buckets: list[ThemeBucket] = field(default_factory=list)
    ticker_buckets: list[TickerBucket] = field(default_factory=list)
    is_provisional: bool = False


@dataclass(slots=True)
class SameDayBundle:
    report_date: date
    chunks: list[SameDayChunk]
    category_buckets: list[CategoryBucket]
    focus_ticker_buckets: list[TickerBucket]
    low_confidence_chunks: list[SameDayChunk]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return list(value)


def _normalize_text_key(value: str | None) -> str:
    return " ".join((value or "").strip().split()).lower()


def _dedupe_chunks(chunks: list[SameDayChunk]) -> list[SameDayChunk]:
    ordered = sorted(chunks, key=lambda chunk: (-chunk.priority_score, chunk.id))
    deduped: list[SameDayChunk] = []
    seen: set[tuple[str | None, str, str | None, str, tuple[str, ...]]] = set()
    for chunk in ordered:
        key = (
            chunk.channel_key,
            chunk.display_category,
            chunk.display_theme,
            _normalize_text_key(chunk.canonical_summary),
            tuple(sorted(_normalize_text_key(ticker) for ticker in chunk.ticker_tags)),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _sorted_chunks(chunks: list[SameDayChunk]) -> list[SameDayChunk]:
    return sorted(chunks, key=lambda chunk: (-chunk.priority_score, chunk.id))


def _build_theme_buckets(category_key: str, chunks: list[SameDayChunk]) -> list[ThemeBucket]:
    grouped: dict[str, list[SameDayChunk]] = defaultdict(list)
    provisional_flags: dict[str, bool] = defaultdict(bool)
    for chunk in chunks:
        theme = chunk.display_theme
        if not theme:
            continue
        grouped[theme].append(chunk)
        provisional_flags[theme] = provisional_flags[theme] or (
            chunk.main_theme is None and chunk.provisional_theme == theme
        )

    buckets = [
        ThemeBucket(
            theme_key=theme,
            category_key=category_key,
            chunks=_sorted_chunks(theme_chunks),
            is_provisional=provisional_flags[theme],
        )
        for theme, theme_chunks in grouped.items()
    ]
    return sorted(buckets, key=lambda bucket: (-len(bucket.chunks), bucket.chunks[0].id))


def _build_ticker_buckets(chunks: list[SameDayChunk]) -> list[TickerBucket]:
    grouped: dict[str, list[SameDayChunk]] = defaultdict(list)
    for chunk in chunks:
        for ticker in chunk.ticker_tags:
            ticker = ticker.strip()
            if ticker:
                grouped[ticker].append(chunk)

    buckets = [
        TickerBucket(ticker=ticker, chunks=_sorted_chunks(ticker_chunks))
        for ticker, ticker_chunks in grouped.items()
    ]
    return sorted(buckets, key=lambda bucket: (-len(bucket.chunks), bucket.chunks[0].id))


def build_same_day_bundle(report_date: date, chunks: list[SameDayChunk]) -> SameDayBundle:
    deduped_chunks = _dedupe_chunks([chunk for chunk in chunks if chunk.source_date == report_date])

    by_category: dict[str, list[SameDayChunk]] = defaultdict(list)
    category_provisional: dict[str, bool] = defaultdict(bool)
    low_confidence_chunks: list[SameDayChunk] = []
    for chunk in deduped_chunks:
        category = chunk.display_category
        by_category[category].append(chunk)
        category_provisional[category] = category_provisional[category] or (
            chunk.category_key == "unclassified" and chunk.provisional_category == category
        )
        if chunk.category_key == "unclassified" and not chunk.provisional_category:
            low_confidence_chunks.append(chunk)

    category_buckets = [
        CategoryBucket(
            category_key=category,
            chunks=_sorted_chunks(category_chunks),
            theme_buckets=_build_theme_buckets(category, category_chunks),
            ticker_buckets=_build_ticker_buckets(category_chunks),
            is_provisional=category_provisional[category],
        )
        for category, category_chunks in by_category.items()
    ]
    category_buckets = sorted(
        category_buckets,
        key=lambda bucket: (-len(bucket.chunks), bucket.category_key),
    )

    return SameDayBundle(
        report_date=report_date,
        chunks=_sorted_chunks(deduped_chunks),
        category_buckets=category_buckets,
        focus_ticker_buckets=_build_ticker_buckets(deduped_chunks),
        low_confidence_chunks=_sorted_chunks(low_confidence_chunks),
    )


def load_same_day_chunks(
    conn: Any,
    report_date: str,
    *,
    source_type: str = KNOWLEDGE_CHUNK_SOURCE_TYPE,
) -> list[SameDayChunk]:
    query = """
    SELECT
        id,
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
        priority_score
    FROM knowledge_chunks
    WHERE source_date = %s
      AND source_type = %s
      AND message_type = ANY(%s)
    ORDER BY priority_score DESC, id ASC;
    """
    with conn.cursor() as cur:
        cur.execute(query, (report_date, source_type, ["signal", "data"]))
        rows = cur.fetchall()

    return [
        SameDayChunk(
            id=row[0],
            source_type=row[1],
            source_pk=row[2],
            source_date=row[3],
            channel_key=row[4],
            message_type=row[5],
            event_type=row[6],
            category_key=row[7],
            main_theme=row[8],
            provisional_category=row[9],
            provisional_theme=row[10],
            is_provisional=row[11],
            sub_themes=_as_list(row[12]),
            ticker_tags=_as_list(row[13]),
            theme_tags=_as_list(row[14]),
            canonical_summary=row[15],
            supporting_facts=_as_list(row[16]),
            evidence_items=_as_list(row[17]),
            qa_warnings=_as_list(row[18]),
            content_clean=row[19],
            priority_score=float(row[20] or 0.0),
        )
        for row in rows
    ]


def load_same_day_bundle(conn: Any, report_date: str) -> SameDayBundle:
    chunks = load_same_day_chunks(conn, report_date)
    return build_same_day_bundle(date.fromisoformat(report_date), chunks)
