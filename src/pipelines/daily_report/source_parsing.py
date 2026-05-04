"""Source parsing utilities for daily report fragments."""

from __future__ import annotations

import re

from src.pipelines.daily_report.models import ArticleFragment, TelegramMessage


_URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
_BUNDLE_MARKER_RE = re.compile(r"(?:^|\n)\s*▶️\s*")


def _extract_first_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0) if match else None


def _normalize_space(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _build_fragment(
    raw_message_id: str,
    channel_id: str,
    chunk_text: str,
    fragment_index: int,
) -> ArticleFragment:
    normalized = _normalize_space(chunk_text)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]

    if lines:
        title = lines[0]
        body = "\n".join(lines[1:]).strip() or title
    else:
        title = ""
        body = ""

    return ArticleFragment(
        fragment_id=f"{raw_message_id}#f{fragment_index}",
        raw_message_id=raw_message_id,
        channel_id=channel_id,
        title=title,
        body=body,
        url=_extract_first_url(normalized),
        fragment_index=fragment_index,
    )


def split_message_into_fragments(
    raw_message_id: str,
    channel_id: str,
    text: str,
) -> list[ArticleFragment]:
    """Split one telegram row into article fragments."""
    normalized = _normalize_space(text)
    if not normalized:
        return []

    chunks: list[str]

    if _BUNDLE_MARKER_RE.search(normalized):
        raw_chunks = _BUNDLE_MARKER_RE.split(normalized)
        chunks = [chunk.strip() for chunk in raw_chunks if chunk.strip()]
    else:
        chunks = [normalized]

    fragments = [
        _build_fragment(
            raw_message_id=raw_message_id,
            channel_id=channel_id,
            chunk_text=chunk,
            fragment_index=index,
        )
        for index, chunk in enumerate(chunks)
    ]
    return fragments


def split_telegram_message(message: TelegramMessage) -> list[ArticleFragment]:
    """Convenience wrapper for TelegramMessage model."""
    raw_message_id = f"{message.channel_id}-{message.message_id}"
    return split_message_into_fragments(
        raw_message_id=raw_message_id,
        channel_id=message.channel_id,
        text=message.text,
    )
