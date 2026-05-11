from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


ProcessingMode = str
MessageType = str


@dataclass(slots=True)
class RawTelegramMessage:
    id: int
    source_date: date
    date_kst: date
    posted_at: datetime
    channel_key: str
    channel_name: str
    channel_message_id: str
    author: str | None
    raw_text: str
    media_info: str | None
    forward_from_channel_key: str | None
    forward_from_channel_name: str | None


@dataclass(slots=True)
class NormalizedMessage:
    telegram_message_id: int
    source_date: date
    date_kst: date
    posted_at: datetime
    channel_key: str
    source_channel_key: str
    source_channel_name: str
    channel_message_id: str
    raw_text: str
    clean_text: str
    urls: list[str]
    has_media: bool
    content_hash: str | None
    processing_mode: ProcessingMode
    grouped_message_ids: list[int]


@dataclass(slots=True)
class ClassifiedMessage:
    telegram_message_id: int
    source_date: date
    channel_key: str
    source_channel_key: str
    processing_mode: ProcessingMode
    message_type: MessageType
    category_key: str
    main_theme: str | None
    sub_themes: list[str]
    ticker_tags: list[str]
    canonical_summary: str
