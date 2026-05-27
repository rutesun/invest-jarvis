from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.stock_report.config import (
    SEMANTIC_EXTRACTION_MAX_RETRIES,
    SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    get_report_synthesis_llm_config,
)
from src.pipelines.stock_report.prompts import (
    REPORT_SYNTHESIS_SYSTEM_PROMPT,
    build_report_synthesis_user_prompt,
)
from src.pipelines.stock_report.retrieval import (
    CategoryBucket,
    SameDayBundle,
    SameDayChunk,
    ThemeBucket,
    TickerBucket,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReportEvidenceRef:
    section_key: str
    item_key: str
    knowledge_chunk_id: int
    rank_score: float
    knowledge_chunk_snapshot: dict[str, Any]


@dataclass(slots=True)
class ReportSectionItem:
    key: str
    title: str
    body: str
    thesis: str | None = None
    evidence_chunk_ids: list[int] = field(default_factory=list)
    evidence_bullets: list[str] = field(default_factory=list)
    impact: str | None = None
    watch_points: list[str] = field(default_factory=list)
    related_categories: list[str] = field(default_factory=list)
    related_stocks: list[dict[str, str | None]] = field(default_factory=list)
    investment_case: str | None = None
    catalysts: list[str] = field(default_factory=list)
    key_metrics: list[str] = field(default_factory=list)
    risks_or_watch_points: list[str] = field(default_factory=list)
    related_themes: list[str] = field(default_factory=list)
    priority_score: float = 0.0


@dataclass(slots=True)
class StockReportArtifact:
    report_date: date
    pulse: list[ReportSectionItem]
    category_summaries: list[ReportSectionItem]
    core_themes: list[ReportSectionItem]
    focus_tickers: list[ReportSectionItem]
    low_confidence_notes: list[str]
    evidence_refs: list[ReportEvidenceRef]


class RelatedStockOutput(BaseModel):
    name: str
    ticker: str | None = None
    catalyst: str

    @field_validator("name", "catalyst", mode="before")
    @classmethod
    def _strip_required(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("ticker", mode="before")
    @classmethod
    def _strip_optional_ticker(cls, value: Any) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class SynthesisPulseItemOutput(BaseModel):
    title: str
    body: str
    evidence_chunk_ids: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class SynthesisCategoryCardOutput(BaseModel):
    category_key: str | None = None
    title: str
    evidence_bullets: list[str] = Field(default_factory=list)
    impact: str
    related_stocks: list[RelatedStockOutput] = Field(default_factory=list)
    evidence_chunk_ids: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class SynthesisCardOutput(BaseModel):
    key: str | None = None
    title: str
    body: str
    evidence_chunk_ids: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class SynthesisCoreThemeOutput(BaseModel):
    key: str | None = None
    title: str
    thesis: str
    evidence_bullets: list[str] = Field(default_factory=list)
    impact: str
    watch_points: list[str] = Field(default_factory=list)
    related_categories: list[str] = Field(default_factory=list)
    related_stocks: list[RelatedStockOutput] = Field(default_factory=list)
    evidence_chunk_ids: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class SynthesisFocusTickerOutput(BaseModel):
    key: str | None = None
    title: str
    investment_case: str
    catalysts: list[str] = Field(default_factory=list)
    key_metrics: list[str] = Field(default_factory=list)
    evidence_bullets: list[str] = Field(default_factory=list)
    risks_or_watch_points: list[str] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class LocalEvidenceSynthesisOutput(BaseModel):
    pulse: list[SynthesisPulseItemOutput] = Field(default_factory=list)
    category_summaries: list[SynthesisCategoryCardOutput] = Field(default_factory=list)
    core_themes: list[SynthesisCoreThemeOutput] = Field(default_factory=list)
    focus_tickers: list[SynthesisFocusTickerOutput] = Field(default_factory=list)


def _join_summaries(chunks: list[SameDayChunk]) -> str:
    summaries = [
        chunk.canonical_summary.strip() for chunk in chunks if chunk.canonical_summary.strip()
    ]
    if not summaries:
        return "요약 가능한 당일 근거가 없습니다."
    return " / ".join(summaries)


def _evidence_refs(
    *,
    section_key: str,
    item_key: str,
    chunks: list[SameDayChunk],
) -> list[ReportEvidenceRef]:
    refs: list[ReportEvidenceRef] = []
    for index, chunk in enumerate(chunks):
        refs.append(
            ReportEvidenceRef(
                section_key=section_key,
                item_key=item_key,
                knowledge_chunk_id=chunk.id,
                rank_score=max(0.0, 1.0 - (index * 0.01)),
                knowledge_chunk_snapshot={
                    "id": chunk.id,
                    "source_type": chunk.source_type,
                    "source_pk": chunk.source_pk,
                    "source_message_db_id": chunk.source_message_db_id,
                    "source_date": chunk.source_date.isoformat(),
                    "channel_key": chunk.channel_key,
                    "channel_name": chunk.channel_name,
                    "channel_message_id": chunk.channel_message_id,
                    "message_type": chunk.message_type,
                    "event_type": chunk.event_type,
                    "category_key": chunk.category_key,
                    "main_theme": chunk.main_theme,
                    "provisional_category": chunk.provisional_category,
                    "provisional_theme": chunk.provisional_theme,
                    "is_provisional": chunk.is_provisional,
                    "sub_themes": chunk.sub_themes,
                    "ticker_tags": chunk.ticker_tags,
                    "theme_tags": chunk.theme_tags,
                    "canonical_summary": chunk.canonical_summary,
                    "supporting_facts": chunk.supporting_facts,
                    "evidence_items": chunk.evidence_items,
                    "qa_warnings": chunk.qa_warnings,
                    "priority_score": chunk.priority_score,
                },
            )
        )
    return refs


def _category_item(bucket: CategoryBucket) -> ReportSectionItem:
    return ReportSectionItem(
        key=bucket.category_key,
        title=bucket.category_key,
        body=_join_summaries(bucket.chunks),
        evidence_chunk_ids=[chunk.id for chunk in bucket.chunks],
    )


def _theme_item(bucket: ThemeBucket) -> ReportSectionItem:
    return ReportSectionItem(
        key=bucket.theme_key,
        title=bucket.theme_key,
        body=_join_summaries(bucket.chunks),
        evidence_chunk_ids=[chunk.id for chunk in bucket.chunks],
    )


def _ticker_item(bucket: TickerBucket) -> ReportSectionItem:
    return ReportSectionItem(
        key=bucket.ticker,
        title=bucket.ticker,
        body=_join_summaries(bucket.chunks),
        evidence_chunk_ids=[chunk.id for chunk in bucket.chunks],
    )


def _build_deterministic_artifact(bundle: SameDayBundle) -> StockReportArtifact:
    category_summaries = [_category_item(bucket) for bucket in bundle.category_buckets]
    core_themes = [
        _theme_item(theme_bucket)
        for category_bucket in bundle.category_buckets
        for theme_bucket in category_bucket.theme_buckets
    ]
    focus_tickers = [_ticker_item(bucket) for bucket in bundle.focus_ticker_buckets]
    low_confidence_notes = [
        chunk.canonical_summary for chunk in bundle.low_confidence_chunks if chunk.canonical_summary
    ]
    pulse_items = [
        ReportSectionItem(
            key=f"pulse-{idx + 1}",
            title=chunk.display_theme or chunk.display_category,
            body=chunk.canonical_summary,
            evidence_chunk_ids=[chunk.id],
        )
        for idx, chunk in enumerate(bundle.chunks[:5])
        if chunk.canonical_summary
    ]
    if not pulse_items:
        pulse_items = [
            ReportSectionItem(
                key="pulse-empty",
                title="데일리 요약",
                body="당일 리포트에 반영할 signal/data chunk가 없습니다.",
                evidence_chunk_ids=[],
            )
        ]

    evidence_refs: list[ReportEvidenceRef] = []
    for bucket in bundle.category_buckets:
        evidence_refs.extend(
            _evidence_refs(
                section_key="category_summaries",
                item_key=bucket.category_key,
                chunks=bucket.chunks,
            )
        )
        for theme_bucket in bucket.theme_buckets:
            evidence_refs.extend(
                _evidence_refs(
                    section_key="core_themes",
                    item_key=theme_bucket.theme_key,
                    chunks=theme_bucket.chunks,
                )
            )
    for ticker_bucket in bundle.focus_ticker_buckets:
        evidence_refs.extend(
            _evidence_refs(
                section_key="focus_tickers",
                item_key=ticker_bucket.ticker,
                chunks=ticker_bucket.chunks,
            )
        )

    return StockReportArtifact(
        report_date=bundle.report_date,
        pulse=pulse_items,
        category_summaries=category_summaries,
        core_themes=core_themes,
        focus_tickers=focus_tickers,
        low_confidence_notes=low_confidence_notes,
        evidence_refs=evidence_refs,
    )


def _index_chunks(bundle: SameDayBundle) -> dict[int, SameDayChunk]:
    return {chunk.id: chunk for chunk in bundle.chunks}


def _sanitize_evidence_ids(ids: list[int], *, allowed: set[int]) -> list[int]:
    return [chunk_id for chunk_id in ids if chunk_id in allowed]


def _sort_by_priority(items: list[ReportSectionItem]) -> list[ReportSectionItem]:
    ordered = sorted(
        enumerate(items),
        key=lambda indexed_item: (-indexed_item[1].priority_score, indexed_item[0]),
    )
    return [item for _, item in ordered]


async def _synthesize_same_day_bundle_with_llm(
    *,
    bundle: SameDayBundle,
    provider: str,
) -> LocalEvidenceSynthesisOutput:
    llm_config = get_report_synthesis_llm_config(provider)
    llm = llm_config.create_llm()
    user_prompt = build_report_synthesis_user_prompt(bundle)
    messages = llm_config.build_messages(REPORT_SYNTHESIS_SYSTEM_PROMPT, user_prompt)
    config = {
        "run_name": f"StockReport Local Evidence Synthesis - {bundle.report_date.isoformat()}",
        "tags": [
            "stock_report",
            "daily_v2",
            "local_evidence_synthesis",
            f"provider:{provider}",
        ],
        "metadata": {
            "stage": "local_evidence_synthesis",
            "report_date": bundle.report_date.isoformat(),
            "provider": provider,
            "model": llm_config.model,
            "chunk_count": len(bundle.chunks),
            "prompt_chars": len(user_prompt),
            "local_mode": True,
            "external_search": "disabled",
        },
    }
    return await invoke_llm_with_retry(
        llm,
        LocalEvidenceSynthesisOutput,
        messages,
        config,
        max_retries=SEMANTIC_EXTRACTION_MAX_RETRIES,
        timeout_seconds=SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    )


def _from_llm_output(
    bundle: SameDayBundle, output: LocalEvidenceSynthesisOutput
) -> StockReportArtifact:
    chunk_by_id = _index_chunks(bundle)
    allowed_ids = set(chunk_by_id.keys())

    pulse = [
        ReportSectionItem(
            key=f"pulse-{idx + 1}",
            title=item.title,
            body=item.body,
            evidence_chunk_ids=_sanitize_evidence_ids(item.evidence_chunk_ids, allowed=allowed_ids),
            priority_score=item.priority_score,
        )
        for idx, item in enumerate(output.pulse[:5])
    ]

    category_summaries = [
        ReportSectionItem(
            key=(item.category_key or item.title),
            title=item.title,
            body=item.impact,
            evidence_chunk_ids=_sanitize_evidence_ids(item.evidence_chunk_ids, allowed=allowed_ids),
            evidence_bullets=item.evidence_bullets[:5],
            impact=item.impact,
            related_stocks=[
                {
                    "name": stock.name,
                    "ticker": stock.ticker,
                    "catalyst": stock.catalyst,
                }
                for stock in item.related_stocks[:5]
            ],
            priority_score=item.priority_score,
        )
        for item in output.category_summaries
    ]
    category_summaries = _sort_by_priority(category_summaries)

    core_themes = [
        ReportSectionItem(
            key=(item.key or item.title),
            title=item.title,
            body=item.thesis,
            thesis=item.thesis,
            evidence_chunk_ids=_sanitize_evidence_ids(item.evidence_chunk_ids, allowed=allowed_ids),
            evidence_bullets=item.evidence_bullets[:6],
            impact=item.impact,
            watch_points=item.watch_points[:5],
            related_categories=item.related_categories[:5],
            related_stocks=[
                {
                    "name": stock.name,
                    "ticker": stock.ticker,
                    "catalyst": stock.catalyst,
                }
                for stock in item.related_stocks[:5]
            ],
            priority_score=item.priority_score,
        )
        for item in output.core_themes
    ]
    core_themes = _sort_by_priority(core_themes)

    focus_tickers = [
        ReportSectionItem(
            key=(item.key or item.title),
            title=item.title,
            body=item.investment_case,
            investment_case=item.investment_case,
            catalysts=item.catalysts,
            key_metrics=item.key_metrics,
            evidence_chunk_ids=_sanitize_evidence_ids(item.evidence_chunk_ids, allowed=allowed_ids),
            evidence_bullets=item.evidence_bullets,
            risks_or_watch_points=item.risks_or_watch_points,
            related_themes=item.related_themes,
            priority_score=item.priority_score,
        )
        for item in output.focus_tickers
    ]
    focus_tickers = _sort_by_priority(focus_tickers)

    low_confidence_notes = [
        chunk.canonical_summary for chunk in bundle.low_confidence_chunks if chunk.canonical_summary
    ]

    evidence_refs: list[ReportEvidenceRef] = []
    for item in pulse:
        chunks = [
            chunk_by_id[chunk_id] for chunk_id in item.evidence_chunk_ids if chunk_id in chunk_by_id
        ]
        evidence_refs.extend(
            _evidence_refs(
                section_key="pulse",
                item_key=item.key,
                chunks=chunks,
            )
        )
    for item in category_summaries:
        chunks = [
            chunk_by_id[chunk_id] for chunk_id in item.evidence_chunk_ids if chunk_id in chunk_by_id
        ]
        evidence_refs.extend(
            _evidence_refs(
                section_key="category_summaries",
                item_key=item.key,
                chunks=chunks,
            )
        )
    for item in core_themes:
        chunks = [
            chunk_by_id[chunk_id] for chunk_id in item.evidence_chunk_ids if chunk_id in chunk_by_id
        ]
        evidence_refs.extend(
            _evidence_refs(
                section_key="core_themes",
                item_key=item.key,
                chunks=chunks,
            )
        )
    for item in focus_tickers:
        chunks = [
            chunk_by_id[chunk_id] for chunk_id in item.evidence_chunk_ids if chunk_id in chunk_by_id
        ]
        evidence_refs.extend(
            _evidence_refs(
                section_key="focus_tickers",
                item_key=item.key,
                chunks=chunks,
            )
        )

    if not pulse:
        pulse = _build_deterministic_artifact(bundle).pulse

    return StockReportArtifact(
        report_date=bundle.report_date,
        pulse=pulse,
        category_summaries=category_summaries,
        core_themes=core_themes,
        focus_tickers=focus_tickers,
        low_confidence_notes=low_confidence_notes,
        evidence_refs=evidence_refs,
    )


def synthesize_same_day_bundle(
    bundle: SameDayBundle,
    *,
    provider: str = "openai",
) -> StockReportArtifact:
    deterministic = _build_deterministic_artifact(bundle)

    try:
        output = asyncio.run(_synthesize_same_day_bundle_with_llm(bundle=bundle, provider=provider))
        llm_artifact = _from_llm_output(bundle, output)
        if (
            llm_artifact.category_summaries
            or llm_artifact.core_themes
            or llm_artifact.focus_tickers
        ):
            return llm_artifact
        logger.warning(
            "Local evidence synthesis output empty, fallback to deterministic: date=%s",
            bundle.report_date,
        )
    except Exception:
        logger.exception(
            "Local evidence synthesis failed, fallback to deterministic: date=%s provider=%s",
            bundle.report_date,
            provider,
        )
    return deterministic
