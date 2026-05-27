from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.retrieval import CategoryBucket, SameDayBundle, SameDayChunk
from src.pipelines.stock_report.synthesize import synthesize_same_day_bundle


def _chunk(
    chunk_id: int,
    *,
    category_key: str = "반도체",
    main_theme: str | None = "HBM",
    ticker_tags: list[str] | None = None,
    canonical_summary: str | None = None,
) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_date=date(2026, 5, 26),
        channel_key="kwusa",
        message_type="signal",
        event_type="해석/전망",
        category_key=category_key,
        main_theme=main_theme,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=ticker_tags or [],
        theme_tags=[],
        canonical_summary=canonical_summary or f"summary-{chunk_id}",
        supporting_facts=[],
        evidence_items=[],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=1.0,
    )


def test_synthesize_same_day_bundle_builds_fixed_sections_from_bundle() -> None:
    nvda_chunk = _chunk(1, ticker_tags=["NVDA"], canonical_summary="NVDA HBM 수요가 강하다")
    samsung_chunk = _chunk(
        2,
        ticker_tags=["삼성전자"],
        canonical_summary="삼성전자 HBM 증설 기대가 이어졌다",
    )
    auto_chunk = _chunk(
        3,
        category_key="자동차",
        main_theme="하이브리드",
        ticker_tags=["현대차"],
        canonical_summary="현대차 하이브리드 전략이 부각됐다",
    )
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=[nvda_chunk, samsung_chunk, auto_chunk],
        category_buckets=[
            CategoryBucket(category_key="반도체", chunks=[nvda_chunk, samsung_chunk]),
            CategoryBucket(category_key="자동차", chunks=[auto_chunk]),
        ],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    artifact = synthesize_same_day_bundle(bundle)

    assert artifact.report_date == date(2026, 5, 26)
    assert artifact.pulse
    assert artifact.pulse == [
        "NVDA HBM 수요가 강하다",
        "삼성전자 HBM 증설 기대가 이어졌다",
        "현대차 하이브리드 전략이 부각됐다",
    ]
    assert [item.title for item in artifact.category_summaries] == ["반도체", "자동차"]
    assert "NVDA HBM 수요가 강하다" in artifact.category_summaries[0].body
    assert "삼성전자 HBM 증설 기대가 이어졌다" in artifact.category_summaries[0].body
    assert {ref.section_key for ref in artifact.evidence_refs} >= {"category_summaries"}
    assert {ref.knowledge_chunk_id for ref in artifact.evidence_refs} == {1, 2, 3}


def test_synthesize_same_day_bundle_keeps_low_confidence_separate() -> None:
    low_confidence = _chunk(
        10,
        category_key="unclassified",
        main_theme=None,
        ticker_tags=[],
        canonical_summary="분류가 애매한 시황",
    )
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=[low_confidence],
        category_buckets=[],
        focus_ticker_buckets=[],
        low_confidence_chunks=[low_confidence],
    )

    artifact = synthesize_same_day_bundle(bundle)

    assert artifact.low_confidence_notes == ["분류가 애매한 시황"]
    assert artifact.category_summaries == []
