from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import timedelta
from typing import Any

from src.pipelines.stock_report.models import NormalizedMessage, RawTelegramMessage


URL_PATTERN = re.compile(r"https?://[^\s)]+")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
MARKDOWN_SYMBOL_PATTERN = re.compile(r"[*_`#>~]")
MULTISPACE_PATTERN = re.compile(r"\s+")


def _canonicalize_text(value: str) -> str:
    text = value.replace("\r\n", "\n")
    text = MARKDOWN_LINK_PATTERN.sub(r"\1", text)
    text = URL_PATTERN.sub(" ", text)
    text = MARKDOWN_SYMBOL_PATTERN.sub(" ", text)
    text = MULTISPACE_PATTERN.sub(" ", text)
    return text.strip()


def _extract_urls(value: str) -> list[str]:
    links: list[str] = []
    for match in MARKDOWN_LINK_PATTERN.finditer(value):
        links.append(match.group(2))

    without_markdown_links = MARKDOWN_LINK_PATTERN.sub(" ", value)
    links.extend(URL_PATTERN.findall(without_markdown_links))

    unique_links: list[str] = []
    seen: set[str] = set()
    for link in links:
        link = link.rstrip(".,")
        if link in seen:
            continue
        seen.add(link)
        unique_links.append(link)
    return unique_links


def _content_hash(clean_text: str) -> str | None:
    if not clean_text:
        return None
    return hashlib.sha1(clean_text.lower().encode("utf-8")).hexdigest()[:16]


def _mark_grouped_only(
    normalized: list[NormalizedMessage],
    *,
    group_window_minutes: int,
    short_comment_max_chars: int,
    short_comment_channels: set[str],
) -> None:
    by_channel: dict[str, list[NormalizedMessage]] = defaultdict(list)

    for item in normalized:
        if item.processing_mode != "full":
            continue
        if item.channel_key not in short_comment_channels:
            continue
        if not item.clean_text or len(item.clean_text) >= short_comment_max_chars:
            continue
        by_channel[item.channel_key].append(item)

    window = timedelta(minutes=group_window_minutes)

    for channel_messages in by_channel.values():
        channel_messages.sort(key=lambda item: item.posted_at)
        groups: list[list[NormalizedMessage]] = []
        current_group: list[NormalizedMessage] = []

        for item in channel_messages:
            if not current_group:
                current_group = [item]
                continue
            if item.posted_at - current_group[-1].posted_at <= window:
                current_group.append(item)
                continue
            groups.append(current_group)
            current_group = [item]

        if current_group:
            groups.append(current_group)

        for group in groups:
            if len(group) < 2:
                continue
            group_ids = [row.telegram_message_id for row in group]
            for row in group:
                row.processing_mode = "grouped_only"
                row.grouped_message_ids = group_ids


def normalize_messages(
    raw_messages: list[RawTelegramMessage],
    *,
    short_comment_channels: set[str],
    short_comment_max_chars: int = 100,
    group_window_minutes: int = 30,
) -> list[NormalizedMessage]:
    normalized: list[NormalizedMessage] = []

    for row in raw_messages:
        urls = _extract_urls(row.raw_text)
        clean_text = _canonicalize_text(row.raw_text)
        has_media = bool(row.media_info)
        processing_mode = "full"

        if not clean_text and not has_media:
            processing_mode = "skip"

        normalized.append(
            NormalizedMessage(
                telegram_message_id=row.id,
                source_date=row.source_date,
                date_kst=row.date_kst,
                posted_at=row.posted_at,
                channel_key=row.channel_key,
                source_channel_key=row.forward_from_channel_key or row.channel_key,
                source_channel_name=row.forward_from_channel_name or row.channel_name,
                channel_message_id=row.channel_message_id,
                raw_text=row.raw_text,
                clean_text=clean_text,
                urls=urls,
                has_media=has_media,
                content_hash=_content_hash(clean_text),
                processing_mode=processing_mode,
                grouped_message_ids=[],
            )
        )

    _mark_grouped_only(
        normalized,
        group_window_minutes=group_window_minutes,
        short_comment_max_chars=short_comment_max_chars,
        short_comment_channels=short_comment_channels,
    )
    return normalized


def persist_normalized_messages(conn: Any, normalized_messages: list[NormalizedMessage]) -> None:
    if not normalized_messages:
        return

    query = """
    UPDATE telegram_messages
    SET
        clean_text = %s,
        urls = %s::jsonb,
        has_media = %s,
        content_hash = %s,
        processing_mode = %s,
        grouped_message_ids = %s,
        updated_at = NOW()
    WHERE id = %s;
    """

    params: list[tuple[Any, ...]] = []
    for item in normalized_messages:
        params.append(
            (
                item.clean_text,
                json.dumps(item.urls, ensure_ascii=False),
                item.has_media,
                item.content_hash,
                item.processing_mode,
                item.grouped_message_ids,
                item.telegram_message_id,
            )
        )

    with conn.cursor() as cur:
        cur.executemany(query, params)
    conn.commit()
