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
    source_message_db_id: int | None
    source_date: date
    channel_key: str | None
    channel_name: str | None
    channel_message_id: str | None
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
        kc.id,
        kc.source_type,
        kc.source_pk,
        kc.source_date,
        kc.channel_key,
        tm.channel_name,
        tm.channel_message_id,
        kc.message_type,
        kc.event_type,
        kc.category_key,
        kc.main_theme,
        kc.provisional_category,
        kc.provisional_theme,
        kc.is_provisional,
        kc.sub_themes,
        kc.ticker_tags,
        kc.theme_tags,
        kc.canonical_summary,
        kc.supporting_facts,
        kc.evidence_items,
        kc.qa_warnings,
        kc.content_clean,
        kc.priority_score
    FROM knowledge_chunks kc
    LEFT JOIN telegram_messages tm ON tm.id = kc.source_pk
    WHERE kc.source_date = %s
      AND kc.source_type = %s
      AND kc.message_type = ANY(%s)
    ORDER BY kc.priority_score DESC, kc.id ASC;
    """
    with conn.cursor() as cur:
        cur.execute(query, (report_date, source_type, ["signal", "data"]))
        rows = cur.fetchall()

    return [
        SameDayChunk(
            id=row[0],
            source_type=row[1],
            source_pk=row[2],
            source_message_db_id=row[2],
            source_date=row[3],
            channel_key=row[4],
            channel_name=row[5],
            channel_message_id=row[6],
            message_type=row[7],
            event_type=row[8],
            category_key=row[9],
            main_theme=row[10],
            provisional_category=row[11],
            provisional_theme=row[12],
            is_provisional=row[13],
            sub_themes=_as_list(row[14]),
            ticker_tags=_as_list(row[15]),
            theme_tags=_as_list(row[16]),
            canonical_summary=row[17],
            supporting_facts=_as_list(row[18]),
            evidence_items=_as_list(row[19]),
            qa_warnings=_as_list(row[20]),
            content_clean=row[21],
            priority_score=float(row[22] or 0.0),
        )
        for row in rows
    ]


def load_same_day_bundle(conn: Any, report_date: str) -> SameDayBundle:
    chunks = load_same_day_chunks(conn, report_date)
    return build_same_day_bundle(date.fromisoformat(report_date), chunks)
