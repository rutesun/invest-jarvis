"""T09-F: per-category / per-ticker map synthesis tests."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from src.pipelines.stock_report.prompts import (
    CATEGORY_CONTEXT_BUDGET_CHARS,
    _trim_entries_to_budget,
)
from src.pipelines.stock_report.retrieval import CategoryBucket, SameDayChunk, TickerBucket
from src.pipelines.stock_report.synthesize import (
    CategoryCardLLMOutput,
    CategorySummaryCard,
    TickerCard,
    TickerCardLLMOutput,
    _render_raw_category_card,
    _render_raw_ticker_card,
    _sanitize_chunk_ids,
    synthesize_category,
    synthesize_ticker,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _chunk(
    chunk_id: int,
    *,
    category_key: str = "반도체",
    priority_score: float = 1.0,
    ticker_tags: list[str] | None = None,
    supporting_facts: list[str] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    canonical_summary: str | None = None,
) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 5, 26),
        channel_key="kwusa",
        channel_name="키움 미국주식",
        channel_message_id=str(50000 + chunk_id),
        message_type="signal",
        event_type="해석/전망",
        category_key=category_key,
        main_theme="HBM",
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=ticker_tags or [],
        theme_tags=[],
        canonical_summary=canonical_summary or f"summary-{chunk_id}",
        supporting_facts=supporting_facts or [f"fact-{chunk_id}"],
        evidence_items=evidence_items or [{"kind": "metric", "text": f"metric-{chunk_id}"}],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=priority_score,
    )


def _category_bucket(chunk_ids: list[int], **chunk_kwargs) -> CategoryBucket:
    chunks = [_chunk(cid, **chunk_kwargs) for cid in chunk_ids]
    return CategoryBucket(category_key="반도체", chunks=chunks)


def _ticker_bucket(chunk_ids: list[int], ticker: str = "NVDA") -> TickerBucket:
    chunks = [_chunk(cid) for cid in chunk_ids]
    return TickerBucket(ticker=ticker, chunks=chunks)


# ---------------------------------------------------------------------------
# _sanitize_chunk_ids
# ---------------------------------------------------------------------------


def test_sanitize_chunk_ids_keeps_valid_integers() -> None:
    result = _sanitize_chunk_ids([1, 2, 3], {1, 2, 3})
    assert result == [1, 2, 3]


def test_sanitize_chunk_ids_removes_out_of_bundle() -> None:
    result = _sanitize_chunk_ids([1, 2, 99], {1, 2})
    assert result == [1, 2]


def test_sanitize_chunk_ids_removes_strings() -> None:
    result = _sanitize_chunk_ids([1, "two", 3, "3"], {1, 3})
    assert result == [1, 3]


def test_sanitize_chunk_ids_empty() -> None:
    result = _sanitize_chunk_ids([], {1, 2})
    assert result == []


def test_sanitize_chunk_ids_all_invalid() -> None:
    result = _sanitize_chunk_ids(["a", "b", 99], {1, 2})
    assert result == []


# ---------------------------------------------------------------------------
# _render_raw_category_card / _render_raw_ticker_card
# ---------------------------------------------------------------------------


def test_render_raw_category_card_uses_bucket_ids() -> None:
    bucket = _category_bucket([10, 20])
    card = _render_raw_category_card(bucket)
    assert isinstance(card, CategorySummaryCard)
    assert card.category_key == "반도체"
    assert card.evidence_chunk_ids == [10, 20]
    assert "summary-10" in card.narrative
    assert "summary-20" in card.narrative


def test_render_raw_category_card_no_llm_call_for_small_bucket() -> None:
    bucket = _category_bucket([1])
    card = _render_raw_category_card(bucket)
    assert card.evidence_chunk_ids == [1]


def test_render_raw_ticker_card() -> None:
    bucket = _ticker_bucket([5, 6])
    card = _render_raw_ticker_card(bucket)
    assert isinstance(card, TickerCard)
    assert card.ticker == "NVDA"
    assert card.evidence_chunk_ids == [5, 6]


# ---------------------------------------------------------------------------
# synthesize_category — raw fallback for chunk_count < 3
# ---------------------------------------------------------------------------


def test_synthesize_category_raw_fallback_below_threshold() -> None:
    bucket = _category_bucket([1, 2])  # < 3 chunks → raw fallback
    card = asyncio.run(synthesize_category(bucket, provider="openai"))
    assert isinstance(card, CategorySummaryCard)
    assert card.evidence_chunk_ids == [1, 2]


def test_synthesize_category_raw_fallback_single_chunk() -> None:
    bucket = _category_bucket([7])
    card = asyncio.run(synthesize_category(bucket, provider="openai"))
    assert card.evidence_chunk_ids == [7]


# ---------------------------------------------------------------------------
# synthesize_category — happy path (mocked LLM)
# ---------------------------------------------------------------------------


def test_synthesize_category_happy_path(monkeypatch) -> None:
    bucket = _category_bucket([1, 2, 3])

    async def _fake_run(system, user, schema, provider):
        assert schema is CategoryCardLLMOutput
        assert "반도체" in user
        return CategoryCardLLMOutput(
            category_key="반도체",
            title="HBM 체인 강세",
            narrative="HBM 수요가 집중됐다. NVDA +5%.",
            evidence_bullets=["NVDA +5%", "SK하이닉스 증설"],
            impact="메모리 밸류체인 심리 개선",
            related_stocks=[{"name": "엔비디아", "ticker": "NVDA", "catalyst": "HBM 수요"}],
            evidence_chunk_ids=[1, 2, 3],
            priority_score=0.85,
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    card = asyncio.run(synthesize_category(bucket, provider="openai"))

    assert card.title == "HBM 체인 강세"
    assert card.narrative == "HBM 수요가 집중됐다. NVDA +5%."
    assert card.evidence_chunk_ids == [1, 2, 3]
    assert card.priority_score == 0.85
    assert card.related_stocks[0]["ticker"] == "NVDA"


def test_synthesize_category_sanitizes_out_of_bundle_ids(monkeypatch) -> None:
    """LLM returns chunk id 99 which is not in the bucket — must be dropped."""
    bucket = _category_bucket([1, 2, 3])

    async def _fake_run(system, user, schema, provider):
        return CategoryCardLLMOutput(
            category_key="반도체",
            title="테스트",
            narrative="테스트 내러티브",
            evidence_bullets=[],
            impact="",
            evidence_chunk_ids=[1, 99, 3],  # 99 is outside bundle
            priority_score=0.5,
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    card = asyncio.run(synthesize_category(bucket, provider="openai"))

    assert 99 not in card.evidence_chunk_ids
    assert card.evidence_chunk_ids == [1, 3]


def test_synthesize_category_llm_failure_falls_back_to_raw(monkeypatch) -> None:
    bucket = _category_bucket([1, 2, 3])

    async def _raise(system, user, schema, provider):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _raise,
    )

    card = asyncio.run(synthesize_category(bucket, provider="openai"))

    # raw fallback — ids are bucket ids
    assert card.evidence_chunk_ids == [1, 2, 3]
    assert "summary-1" in card.narrative


# ---------------------------------------------------------------------------
# synthesize_ticker — raw fallback and happy path
# ---------------------------------------------------------------------------


def test_synthesize_ticker_raw_fallback_below_threshold() -> None:
    bucket = _ticker_bucket([1])
    card = asyncio.run(synthesize_ticker(bucket, provider="openai"))
    assert isinstance(card, TickerCard)
    assert card.evidence_chunk_ids == [1]


def test_synthesize_ticker_happy_path(monkeypatch) -> None:
    bucket = _ticker_bucket([1, 2, 3])

    async def _fake_run(system, user, schema, provider):
        assert schema is TickerCardLLMOutput
        return TickerCardLLMOutput(
            ticker="NVDA",
            investment_case="AI 서버 수요로 HBM 전량 수주 확보",
            catalysts=["Blackwell 출시", "GTC 발표"],
            key_metrics=["매출 +122% YoY"],
            risks=["공급 지연"],
            evidence_chunk_ids=[1, 2, 3],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    card = asyncio.run(synthesize_ticker(bucket, provider="openai"))

    assert card.ticker == "NVDA"
    assert card.investment_case == "AI 서버 수요로 HBM 전량 수주 확보"
    assert card.evidence_chunk_ids == [1, 2, 3]
    assert card.key_metrics == ["매출 +122% YoY"]


def test_synthesize_ticker_llm_failure_falls_back_to_raw(monkeypatch) -> None:
    bucket = _ticker_bucket([10, 11, 12])

    async def _raise(system, user, schema, provider):
        raise RuntimeError("timeout")

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _raise,
    )

    card = asyncio.run(synthesize_ticker(bucket, provider="openai"))

    assert card.ticker == "NVDA"
    assert card.evidence_chunk_ids == [10, 11, 12]


def test_synthesize_ticker_sanitizes_out_of_bundle_ids(monkeypatch) -> None:
    bucket = _ticker_bucket([1, 2, 3])

    async def _fake_run(system, user, schema, provider):
        return TickerCardLLMOutput(
            ticker="NVDA",
            investment_case="테스트",
            evidence_chunk_ids=[1, 3, 999],  # 999 is out-of-bundle
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    card = asyncio.run(synthesize_ticker(bucket, provider="openai"))

    assert card.evidence_chunk_ids == [1, 3]


# ---------------------------------------------------------------------------
# Context budget: _trim_entries_to_budget
# ---------------------------------------------------------------------------


def _make_fat_entries(n: int, items_per_chunk: int = 100) -> list[dict]:
    """Create entries with many evidence_items to simulate a large category."""
    entries = []
    for i in range(n):
        entries.append(
            {
                "chunk_id": i + 1,
                "message_type": "signal",
                "priority_score": float(i),  # ascending so lowest = first trimmed
                "tickers": ["NVDA"],
                "canonical_summary": f"summary-{i}",
                "supporting_facts": [f"fact-{i}-{j}" for j in range(20)],
                "evidence_items": [
                    {"kind": "metric", "text": f"metric-{i}-{j}" * 10}
                    for j in range(items_per_chunk)
                ],
                "source": f"channel#{i}",
            }
        )
    return entries


def test_trim_entries_no_trim_needed() -> None:
    entries = [
        {
            "chunk_id": 1,
            "priority_score": 1.0,
            "supporting_facts": ["f1"],
            "evidence_items": [{"kind": "fact", "text": "short"}],
        }
    ]
    result = _trim_entries_to_budget(entries, CATEGORY_CONTEXT_BUDGET_CHARS)
    assert len(result) == 1
    assert result[0]["evidence_items"] == [{"kind": "fact", "text": "short"}]


def test_trim_entries_reduces_evidence_items_when_over_budget() -> None:
    entries = _make_fat_entries(n=5, items_per_chunk=200)
    import json

    original_size = len(json.dumps(entries, ensure_ascii=False))
    assert original_size > CATEGORY_CONTEXT_BUDGET_CHARS, "Test setup: entries must exceed budget"

    result = _trim_entries_to_budget(entries, CATEGORY_CONTEXT_BUDGET_CHARS)
    result_size = len(json.dumps(result, ensure_ascii=False))
    assert result_size <= CATEGORY_CONTEXT_BUDGET_CHARS


def test_trim_entries_trims_lowest_priority_first() -> None:
    """Highest-priority chunk's evidence_items should be preserved longer."""
    import json

    # Use a tight budget that the 2-chunk payload will exceed
    tight_budget = 3000

    # 2 chunks: low (priority=0.1) and high (priority=0.9), both fat enough
    # to exceed tight_budget when combined
    low = {
        "chunk_id": 1,
        "priority_score": 0.1,
        "supporting_facts": [f"lf{i}" for i in range(30)],
        "evidence_items": [{"kind": "metric", "text": f"LOW-metric-{i}" * 10} for i in range(30)],
        "source": "ch#1",
    }
    high = {
        "chunk_id": 2,
        "priority_score": 0.9,
        "supporting_facts": [f"hf{i}" for i in range(30)],
        "evidence_items": [{"kind": "metric", "text": f"HIGH-metric-{i}" * 10} for i in range(30)],
        "source": "ch#2",
    }
    entries = [low, high]
    assert len(json.dumps(entries, ensure_ascii=False)) > tight_budget, (
        "Test setup: entries must exceed tight_budget"
    )

    result = _trim_entries_to_budget(entries, tight_budget)

    # Find the high-priority entry in result (by chunk_id)
    high_result = next((e for e in result if e.get("chunk_id") == 2), None)
    low_result = next((e for e in result if e.get("chunk_id") == 1), None)

    result_size = len(json.dumps(result, ensure_ascii=False))
    assert result_size <= tight_budget

    if high_result and low_result:
        # High-priority chunk should have more items remaining than low-priority
        assert len(high_result.get("evidence_items", [])) >= len(
            low_result.get("evidence_items", [])
        )


def test_trim_entries_context_budget_via_build_category_synthesis_prompt() -> None:
    """End-to-end: the trimmed evidence JSON embedded in the prompt must fit the budget.

    The prompt itself includes fixed instruction text (~1-2KB), so we check that the
    evidence JSON portion (extracted via _build_category_chunk_entries + trim) fits
    within CATEGORY_CONTEXT_BUDGET_CHARS.  The full prompt may be slightly larger due
    to prompt instructions overhead, but the JSON payload must be within budget.
    """
    import json as _json

    from src.pipelines.stock_report.prompts import _build_category_chunk_entries

    # Create a bucket with many large chunks that would exceed the budget without trimming
    chunks = []
    for i in range(1, 30):
        chunks.append(
            _chunk(
                i,
                supporting_facts=[f"fact-{i}-{j}" for j in range(20)],
                evidence_items=[
                    {"kind": "metric", "text": f"metric-{i}-{j}" * 10} for j in range(50)
                ],
            )
        )
    bucket = CategoryBucket(category_key="반도체", chunks=chunks)

    entries = _build_category_chunk_entries(bucket)
    original_size = len(_json.dumps(entries, ensure_ascii=False))
    assert original_size > CATEGORY_CONTEXT_BUDGET_CHARS, (
        "Test setup: raw entries must exceed the budget to exercise trimming"
    )

    trimmed = _trim_entries_to_budget(entries, CATEGORY_CONTEXT_BUDGET_CHARS)
    trimmed_size = len(_json.dumps(trimmed, ensure_ascii=False))
    assert trimmed_size <= CATEGORY_CONTEXT_BUDGET_CHARS


def test_trim_entries_pass3_drops_lowest_priority_chunks_first() -> None:
    """Pass 3 must drop the LOWEST-priority chunk first, not the highest.

    Budget is set so small that Passes 1 and 2 cannot reach it (each chunk has
    only 1 evidence_item and 1 supporting_fact, so there is nothing left to trim
    at the item level).  Pass 3 must therefore drop whole chunks, and it must
    drop the lowest-priority one first.
    """
    import json as _json

    # Three minimal chunks so each has nothing to trim at the item level.
    # priority_score: low=0.1, mid=0.5, high=0.9
    low = {
        "chunk_id": 10,
        "priority_score": 0.1,
        "supporting_facts": ["low-fact"],
        "evidence_items": [{"kind": "metric", "text": "low-evidence-payload-" * 20}],
        "source": "ch#low",
    }
    mid = {
        "chunk_id": 20,
        "priority_score": 0.5,
        "supporting_facts": ["mid-fact"],
        "evidence_items": [{"kind": "metric", "text": "mid-evidence-payload-" * 20}],
        "source": "ch#mid",
    }
    high = {
        "chunk_id": 30,
        "priority_score": 0.9,
        "supporting_facts": ["high-fact"],
        "evidence_items": [{"kind": "metric", "text": "high-evidence-payload-" * 20}],
        "source": "ch#high",
    }
    entries = [low, mid, high]

    # Budget that fits exactly 1 chunk (each chunk is ~400-600 chars; 1 chunk ~ 500 max)
    one_chunk_size = max(len(_json.dumps([e], ensure_ascii=False)) for e in entries)
    tight_budget = one_chunk_size + 50  # fits 1 chunk, not 2 or 3

    full_size = len(_json.dumps(entries, ensure_ascii=False))
    assert full_size > tight_budget, "Test setup: all 3 chunks must exceed the budget"

    result = _trim_entries_to_budget(entries, tight_budget)
    result_size = len(_json.dumps(result, ensure_ascii=False))
    assert result_size <= tight_budget, "Result must fit within the budget"

    # The high-priority chunk (chunk_id=30) must be present in the result.
    chunk_ids_in_result = [e["chunk_id"] for e in result]
    assert 30 in chunk_ids_in_result, (
        f"Highest-priority chunk (id=30) must be retained; result ids: {chunk_ids_in_result}"
    )
    # The lowest-priority chunk (chunk_id=10) must have been dropped.
    assert 10 not in chunk_ids_in_result, (
        f"Lowest-priority chunk (id=10) must be dropped first; result ids: {chunk_ids_in_result}"
    )
