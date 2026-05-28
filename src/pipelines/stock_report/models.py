from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ProcessingMode = str
MessageType = str
StructureType = str
EvidenceKind = Literal[
    "fact",
    "metric",
    "thesis",
    "risk",
    "market_context",
    "author_comment",
]
ALLOWED_EVIDENCE_KINDS = {
    "fact",
    "metric",
    "thesis",
    "risk",
    "market_context",
    "author_comment",
}


class QAWarning(BaseModel):
    code: str
    detail: str | None = None
    evidence_index: int | None = None

    @field_validator("code", mode="before")
    @classmethod
    def strip_code(cls, value: str) -> str:
        return str(value).strip()

    @field_validator("detail", mode="before")
    @classmethod
    def strip_detail(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class EvidenceItem(BaseModel):
    kind: EvidenceKind
    text: str
    raw_kind: str | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_unknown_kind(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        kind = str(data.get("kind") or "fact").strip()
        if kind not in ALLOWED_EVIDENCE_KINDS:
            data = dict(data)
            data["raw_kind"] = kind
            data["kind"] = "fact"
        return data

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return str(value).strip()


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
    provisional_category: str | None
    provisional_theme: str | None
    is_provisional: bool
    sub_themes: list[str]
    ticker_tags: list[str]
    canonical_summary: str
    supporting_facts: list[str]
    raw_message_type: str | None = None
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    qa_warnings: list[QAWarning] = field(default_factory=list)


class SemanticUnitLLMOutput(BaseModel):
    message_type: Literal["signal", "opinion", "data", "admin"]
    event_type: str | None = None
    category_key: str | None = None
    main_theme: str | None = None
    sub_themes: list[str] = Field(default_factory=list)
    ticker_tags: list[str] = Field(default_factory=list)
    canonical_summary: str
    evidence_items: list[EvidenceItem] = Field(default_factory=list)

    @field_validator("event_type", "category_key", "main_theme", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("sub_themes", "ticker_tags", mode="before")
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


class SemanticUnitDraft(SemanticUnitLLMOutput):
    supporting_facts: list[str] = Field(default_factory=list)

    @field_validator("supporting_facts", mode="before")
    @classmethod
    def normalize_supporting_facts(cls, value: list[str] | None) -> list[str]:
        return cls.normalize_text_list(value)


class SemanticExtractionLLMOutput(BaseModel):
    structure_type: Literal[
        "single_topic_deep",
        "multi_item_digest",
        "market_wrap",
        "notice",
    ]
    units: list[SemanticUnitLLMOutput] = Field(default_factory=list)


class SemanticExtractionDraft(BaseModel):
    structure_type: Literal[
        "single_topic_deep",
        "multi_item_digest",
        "market_wrap",
        "notice",
    ]
    units: list[SemanticUnitDraft] = Field(default_factory=list)
