"""Tests for the deterministic high-impact-event safety net."""

from __future__ import annotations

import logging
from datetime import date

from src.pipelines.stock_report.event_safety_net import (
    HIGH_IMPACT_EVENT_TYPES,
    enforce_high_impact_event_coverage,
)
from src.pipelines.stock_report.prompts import (
    CANONICAL_EVENT_TYPES,
    SEMANTIC_EXTRACTION_SYSTEM_PROMPT,
)
from src.pipelines.stock_report.retrieval import SameDayChunk
from src.pipelines.stock_report.synthesize import CategorySummaryCard


def _chunk(
    chunk_id: int,
    *,
    event_type: str = "실적",
    priority_score: float = 1.0,
    canonical_summary: str | None = None,
    supporting_facts: list[str] | None = None,
    category_key: str = "소비재/유통",
) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 5, 28),
        channel_key="ch",
        channel_name="채널",
        channel_message_id=str(50000 + chunk_id),
        message_type="signal",
        event_type=event_type,
        category_key=category_key,
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        theme_tags=[],
        canonical_summary=(
            f"summary-{chunk_id}" if canonical_summary is None else canonical_summary
        ),
        supporting_facts=supporting_facts if supporting_facts is not None else [f"fact-{chunk_id}"],
        evidence_items=[],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=priority_score,
    )


def _card(
    evidence_chunk_ids: list[int], *, bullets: list[str] | None = None
) -> CategorySummaryCard:
    return CategorySummaryCard(
        category_key="소비재/유통",
        title="소비재/유통",
        narrative="LLM이 작성한 종합 서사.",
        evidence_bullets=list(bullets) if bullets is not None else ["기존 불릿"],
        impact="중립",
        related_stocks=[],
        evidence_chunk_ids=list(evidence_chunk_ids),
        priority_score=1.0,
    )


def test_dropped_mna_is_surfaced() -> None:
    card = _card([1])
    chunks = [
        _chunk(1, event_type="실적"),
        _chunk(2, event_type="M&A", canonical_summary="우버, 딜리버리히어로 지분 36.83% 확대"),
    ]

    result = enforce_high_impact_event_coverage(card, chunks)

    assert 2 in result.evidence_chunk_ids
    assert any("우버" in bullet for bullet in result.evidence_bullets)
    assert any(bullet.startswith("[M&A]") for bullet in result.evidence_bullets)


def test_cited_mna_is_not_duplicated() -> None:
    card = _card([1, 2])
    chunks = [
        _chunk(1, event_type="실적"),
        _chunk(2, event_type="M&A", canonical_summary="이미 인용된 인수 건"),
    ]

    result = enforce_high_impact_event_coverage(card, chunks)

    assert result.evidence_chunk_ids == [1, 2]
    assert result.evidence_bullets == ["기존 불릿"]


def test_non_high_impact_event_is_not_surfaced() -> None:
    card = _card([1])
    chunks = [
        _chunk(1, event_type="실적"),
        _chunk(2, event_type="해석/전망", canonical_summary="단순 전망 코멘트"),
        _chunk(3, event_type="수주/계약", canonical_summary="평범한 계약"),
    ]

    result = enforce_high_impact_event_coverage(card, chunks)

    assert result.evidence_chunk_ids == [1]
    assert result.evidence_bullets == ["기존 불릿"]


def test_capital_raise_is_surfaced_but_noncanonical_buyback_is_not() -> None:
    card = _card([])
    chunks = [
        _chunk(10, event_type="자본조달", canonical_summary="블랙스톤 131억달러 펀드"),
        _chunk(11, event_type="자사주매입", canonical_summary="대규모 자사주 매입 공시"),
    ]

    result = enforce_high_impact_event_coverage(card, chunks)

    # 자본조달 is high-impact; 자사주매입 is intentionally NOT a trigger (non-canonical,
    # folded into 자본조달) — see HIGH_IMPACT_EVENT_TYPES rationale.
    assert result.evidence_chunk_ids == [10]


def test_cap_limits_supplements_to_highest_priority() -> None:
    card = _card([])
    chunks = [
        _chunk(20, event_type="M&A", priority_score=0.2, canonical_summary="저우선 M&A"),
        _chunk(21, event_type="M&A", priority_score=0.9, canonical_summary="고우선 M&A"),
        _chunk(22, event_type="M&A", priority_score=0.5, canonical_summary="중간 M&A"),
    ]

    result = enforce_high_impact_event_coverage(card, chunks, max_supplements=1)

    assert result.evidence_chunk_ids == [21]
    # one original bullet + exactly one surfaced supplement (cap=1)
    assert result.evidence_bullets == ["기존 불릿", "[M&A] 고우선 M&A (fact-21)"]


def test_empty_summary_chunk_is_skipped() -> None:
    card = _card([])
    chunks = [_chunk(30, event_type="M&A", canonical_summary="   ")]

    result = enforce_high_impact_event_coverage(card, chunks)

    assert result.evidence_chunk_ids == []
    assert result.evidence_bullets == ["기존 불릿"]


def test_supplement_format_includes_event_and_fact() -> None:
    card = _card([])
    chunks = [
        _chunk(
            40,
            event_type="M&A",
            canonical_summary="MGM 인수 제안",
            supporting_facts=["180억달러 규모, +15%"],
        )
    ]

    result = enforce_high_impact_event_coverage(card, chunks)

    assert result.evidence_bullets[-1] == "[M&A] MGM 인수 제안 (180억달러 규모, +15%)"


def test_no_candidates_returns_card_unchanged() -> None:
    card = _card([1])
    chunks = [_chunk(1, event_type="실적")]

    result = enforce_high_impact_event_coverage(card, chunks)

    assert result is card
    assert result.evidence_chunk_ids == [1]
    assert result.evidence_bullets == ["기존 불릿"]


def test_tie_break_prefers_lower_chunk_id() -> None:
    card = _card([])
    chunks = [
        _chunk(52, event_type="M&A", priority_score=0.5, canonical_summary="동률 B"),
        _chunk(51, event_type="M&A", priority_score=0.5, canonical_summary="동률 A"),
    ]

    result = enforce_high_impact_event_coverage(card, chunks, max_supplements=1)

    assert result.evidence_chunk_ids == [51]


def test_cap_equal_to_candidate_count_surfaces_all() -> None:
    card = _card([])
    chunks = [
        _chunk(60, event_type="M&A", priority_score=0.9),
        _chunk(61, event_type="자본조달", priority_score=0.8),
    ]

    result = enforce_high_impact_event_coverage(card, chunks, max_supplements=2)

    assert set(result.evidence_chunk_ids) == {60, 61}


def test_default_cap_truncates_and_warns(caplog) -> None:
    card = _card([])
    chunks = [
        _chunk(70 + i, event_type="M&A", priority_score=1.0 - i * 0.01)
        for i in range(6)  # 6 candidates vs default cap of 5
    ]

    with caplog.at_level(logging.WARNING):
        result = enforce_high_impact_event_coverage(card, chunks)

    surfaced = [b for b in result.evidence_bullets if b.startswith("[M&A]")]
    assert len(surfaced) == 5
    assert len(result.evidence_chunk_ids) == 5
    assert any("cap hit" in r.getMessage() for r in caplog.records)


def test_high_impact_is_subset_of_canonical_taxonomy() -> None:
    # drift guard: a high-impact type missing from the canonical set would never be emitted
    assert HIGH_IMPACT_EVENT_TYPES <= CANONICAL_EVENT_TYPES


def test_high_impact_types_are_instructed_in_extraction_prompt() -> None:
    # root-cause guard for the original blocker: every protected event_type must actually
    # be one the extraction LLM is told to emit, else the net is a silent no-op.
    for event_type in HIGH_IMPACT_EVENT_TYPES:
        assert event_type in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
