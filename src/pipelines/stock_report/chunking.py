from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from src.pipelines.stock_report.models import ClassifiedMessage, NormalizedMessage


CHUNK_TARGET_MESSAGE_TYPES = {"signal", "data"}
KNOWLEDGE_CHUNK_SOURCE_TYPE = "telegram_unit_v2"


@dataclass(slots=True)
class ChunkDraft:
    source_type: str
    source_pk: int | None
    source_date: date
    channel_key: str
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
    content_clean: str
    embed_payload: str
    channel_weight: float
    priority_score: float


def build_embed_payload(
    *,
    canonical_summary: str,
    clean_text: str,
    channel_name: str,
    category_key: str,
    main_theme: str | None,
    ticker_tags: list[str],
) -> str:
    ticker_text = ", ".join(ticker_tags[:5]) if ticker_tags else "-"
    theme_text = main_theme or "-"
    return (
        f"채널: {channel_name}\n"
        f"카테고리: {category_key}\n"
        f"메인테마: {theme_text}\n"
        f"티커: {ticker_text}\n"
        f"{canonical_summary}\n"
        f"{clean_text}"
    )


def resolve_effective_taxonomy(
    *,
    category_key: str,
    main_theme: str | None,
    provisional_category: str | None,
    provisional_theme: str | None,
) -> tuple[str, str | None]:
    effective_category = category_key
    if effective_category == "unclassified" and provisional_category:
        effective_category = provisional_category
    effective_theme = main_theme or provisional_theme
    return effective_category, effective_theme


def _estimate_priority_score(message_type: str) -> float:
    if message_type == "signal":
        return 1.0
    if message_type == "data":
        return 0.8
    if message_type == "opinion":
        return 0.6
    return 0.2


def _build_grouped_only_summary(rows: list[NormalizedMessage]) -> str:
    fragments = [row.clean_text.strip() for row in rows if row.clean_text.strip()]
    if not fragments:
        return "단기 시황 묶음"
    summary = " | ".join(fragments[:3])
    return summary[:180].rstrip()


def _build_grouped_only_chunk(
    rows: list[NormalizedMessage],
    *,
    source_date: date,
) -> ChunkDraft:
    ordered_rows = sorted(rows, key=lambda row: row.posted_at)
    first = ordered_rows[0]
    grouped_ids = sorted({row.telegram_message_id for row in ordered_rows})
    clean_text = "\n".join(row.clean_text.strip() for row in ordered_rows if row.clean_text.strip())
    canonical_summary = _build_grouped_only_summary(ordered_rows)
    payload = build_embed_payload(
        canonical_summary=canonical_summary,
        clean_text=clean_text,
        channel_name=first.source_channel_name,
        category_key="unclassified",
        main_theme=None,
        ticker_tags=[],
    )
    return ChunkDraft(
        source_type=KNOWLEDGE_CHUNK_SOURCE_TYPE,
        source_pk=grouped_ids[0] if grouped_ids else first.telegram_message_id,
        source_date=source_date,
        channel_key=first.channel_key,
        message_type="data",
        event_type="통계/지표",
        category_key="unclassified",
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        theme_tags=[],
        canonical_summary=canonical_summary,
        supporting_facts=[f"grouped_message_ids={json.dumps(grouped_ids, ensure_ascii=False)}"],
        content_clean=clean_text,
        embed_payload=payload,
        channel_weight=1.0,
        priority_score=_estimate_priority_score("data"),
    )


def build_chunk_drafts(
    *,
    normalized_messages: list[NormalizedMessage],
    classified_messages: list[ClassifiedMessage],
) -> list[ChunkDraft]:
    if not normalized_messages:
        return []

    normalized_by_id = {row.telegram_message_id: row for row in normalized_messages}
    drafts: list[ChunkDraft] = []

    for item in classified_messages:
        if item.message_type not in CHUNK_TARGET_MESSAGE_TYPES:
            continue

        normalized = normalized_by_id.get(item.telegram_message_id)
        if normalized is None:
            continue
        if normalized.processing_mode == "grouped_only":
            continue

        theme_tags: list[str] = []
        if item.main_theme:
            theme_tags.append(item.main_theme)
        theme_tags.extend(item.sub_themes)
        effective_category, effective_main_theme = resolve_effective_taxonomy(
            category_key=item.category_key,
            main_theme=item.main_theme,
            provisional_category=item.provisional_category,
            provisional_theme=item.provisional_theme,
        )

        payload = build_embed_payload(
            canonical_summary=item.canonical_summary,
            clean_text=normalized.clean_text,
            channel_name=normalized.source_channel_name,
            category_key=effective_category,
            main_theme=effective_main_theme,
            ticker_tags=item.ticker_tags,
        )

        drafts.append(
            ChunkDraft(
                source_type=KNOWLEDGE_CHUNK_SOURCE_TYPE,
                source_pk=item.telegram_message_id,
                source_date=item.source_date,
                channel_key=item.channel_key,
                message_type=item.message_type,
                event_type=item.event_type,
                category_key=item.category_key,
                main_theme=item.main_theme,
                provisional_category=item.provisional_category,
                provisional_theme=item.provisional_theme,
                is_provisional=item.is_provisional,
                sub_themes=item.sub_themes,
                ticker_tags=item.ticker_tags,
                theme_tags=theme_tags,
                canonical_summary=item.canonical_summary,
                supporting_facts=item.supporting_facts,
                content_clean=normalized.clean_text,
                embed_payload=payload,
                channel_weight=1.0,
                priority_score=_estimate_priority_score(item.message_type),
            )
        )

    grouped_candidates: dict[tuple[int, ...], list[NormalizedMessage]] = {}
    for row in normalized_messages:
        if row.processing_mode != "grouped_only":
            continue
        if not row.grouped_message_ids:
            continue
        group_key = tuple(sorted(set(row.grouped_message_ids)))
        if not group_key:
            continue
        grouped_candidates.setdefault(group_key, []).append(row)

    for group_key in sorted(grouped_candidates):
        group_rows = grouped_candidates[group_key]
        if not group_rows:
            continue
        source_date = group_rows[0].source_date
        drafts.append(_build_grouped_only_chunk(group_rows, source_date=source_date))

    return drafts
