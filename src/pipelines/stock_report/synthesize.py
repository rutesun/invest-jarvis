from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.pipelines.stock_report.retrieval import (
    CategoryBucket,
    SameDayBundle,
    SameDayChunk,
    ThemeBucket,
    TickerBucket,
)


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
    evidence_chunk_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class StockReportArtifact:
    report_date: date
    pulse: list[str]
    category_summaries: list[ReportSectionItem]
    core_themes: list[ReportSectionItem]
    focus_tickers: list[ReportSectionItem]
    low_confidence_notes: list[str]
    evidence_refs: list[ReportEvidenceRef]


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
                    "source_date": chunk.source_date.isoformat(),
                    "channel_key": chunk.channel_key,
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


def _build_pulse(bundle: SameDayBundle) -> list[str]:
    if not bundle.chunks:
        return ["당일 리포트에 반영할 signal/data chunk가 없습니다."]

    return [chunk.canonical_summary for chunk in bundle.chunks[:5] if chunk.canonical_summary]


def synthesize_same_day_bundle(bundle: SameDayBundle) -> StockReportArtifact:
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
        pulse=_build_pulse(bundle),
        category_summaries=category_summaries,
        core_themes=core_themes,
        focus_tickers=focus_tickers,
        low_confidence_notes=low_confidence_notes,
        evidence_refs=evidence_refs,
    )
