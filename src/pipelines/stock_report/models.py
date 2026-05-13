from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ProcessingMode = str
MessageType = str
StructureType = str


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
    structure_type: StructureType
    unit_index: int
    message_type: MessageType
    event_type: str | None
    category_key: str
    main_theme: str | None
    sub_themes: list[str]
    ticker_tags: list[str]
    canonical_summary: str
    supporting_facts: list[str]


class SemanticUnitDraft(BaseModel):
    message_type: Literal["signal", "opinion", "data", "admin"]
    event_type: str | None = None
    category_key: str | None = None
    main_theme: str | None = None
    sub_themes: list[str] = Field(default_factory=list)
    ticker_tags: list[str] = Field(default_factory=list)
    canonical_summary: str
    supporting_facts: list[str] = Field(default_factory=list)

    @field_validator("event_type", "category_key", "main_theme", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("sub_themes", "ticker_tags", "supporting_facts", mode="before")
    @classmethod
    def normalize_text_list(cls, value: list[str] | None) -> list[str]:
        if not value:
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            stripped = item.strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized

    @field_validator("canonical_summary", mode="before")
    @classmethod
    def strip_canonical_summary(cls, value: str) -> str:
        return value.strip()


class SemanticExtractionDraft(BaseModel):
    structure_type: Literal[
        "single_topic_deep",
        "multi_item_digest",
        "market_wrap",
        "notice",
    ]
    units: list[SemanticUnitDraft] = Field(default_factory=list)
