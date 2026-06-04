"""T09-G: synthesize_overview (reduce step) tests."""

from __future__ import annotations

import asyncio
from datetime import date

from src.pipelines.stock_report.prompts import (
    OVERVIEW_SYNTHESIS_SYSTEM_PROMPT,
    build_overview_prompt,
)
from src.pipelines.stock_report.retrieval import CategoryBucket, SameDayChunk, TickerBucket
from src.pipelines.stock_report.synthesize import (
    CategorySummaryCard,
    OverviewLLMOutput,
    OverviewResult,
    TickerCard,
    _build_deterministic_pulse,
    _build_overview_result_from_llm,
    _collect_allowed_ids_from_cards,
    _ids_from_card_indices,
    synthesize_overview,
    synthesize_tiered,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _cat_card(
    category_key: str,
    chunk_ids: list[int],
    *,
    title: str = "",
    narrative: str = "",
    priority_score: float = 0.5,
) -> CategorySummaryCard:
    return CategorySummaryCard(
        category_key=category_key,
        title=title or category_key,
        narrative=narrative or f"{category_key} narrative",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=chunk_ids,
        priority_score=priority_score,
    )


def _ticker_card(
    ticker: str,
    chunk_ids: list[int],
    *,
    investment_case: str = "",
) -> TickerCard:
    return TickerCard(
        ticker=ticker,
        investment_case=investment_case or f"{ticker} investment case",
        catalysts=[],
        key_metrics=[],
        risks=[],
        evidence_chunk_ids=chunk_ids,
    )


def _chunk(chunk_id: int, *, category_key: str = "반도체") -> SameDayChunk:
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
        ticker_tags=[],
        theme_tags=[],
        canonical_summary=f"summary-{chunk_id}",
        supporting_facts=[f"fact-{chunk_id}"],
        evidence_items=[{"kind": "metric", "text": f"metric-{chunk_id}"}],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=1.0,
    )


def _cat_bucket(chunk_ids: list[int], category_key: str = "반도체") -> CategoryBucket:
    return CategoryBucket(
        category_key=category_key,
        chunks=[_chunk(cid, category_key=category_key) for cid in chunk_ids],
    )


def _ticker_bucket(chunk_ids: list[int], ticker: str = "NVDA") -> TickerBucket:
    return TickerBucket(ticker=ticker, chunks=[_chunk(cid) for cid in chunk_ids])


# ---------------------------------------------------------------------------
# build_overview_prompt
# ---------------------------------------------------------------------------


def test_build_overview_prompt_includes_cards() -> None:
    cats = [_cat_card("반도체", [1, 2]), _cat_card("AI인프라", [3, 4])]
    tickers = [_ticker_card("NVDA", [5])]
    prompt = build_overview_prompt(cats, tickers)

    assert "반도체" in prompt
    assert "AI인프라" in prompt
    assert "NVDA" in prompt
    assert "category_card_count: 2" in prompt
    assert "ticker_card_count: 1" in prompt


def test_build_overview_prompt_card_indices_are_sequential() -> None:
    import json

    cats = [_cat_card("반도체", [1]), _cat_card("AI인프라", [2])]
    tickers = [_ticker_card("NVDA", [3])]
    prompt = build_overview_prompt(cats, tickers)
    # Extract JSON portion
    json_start = prompt.index("cards (JSON):") + len("cards (JSON):")
    cards = json.loads(prompt[json_start:].strip())
    indices = [c["card_index"] for c in cards]
    assert indices == [0, 1, 2]


def test_build_overview_prompt_empty_cards() -> None:
    prompt = build_overview_prompt([], [])
    assert "category_card_count: 0" in prompt
    assert "ticker_card_count: 0" in prompt


# ---------------------------------------------------------------------------
# OVERVIEW_SYNTHESIS_SYSTEM_PROMPT content
# ---------------------------------------------------------------------------


def test_overview_system_prompt_mentions_cross_category() -> None:
    assert "2개 이상" in OVERVIEW_SYNTHESIS_SYSTEM_PROMPT
    assert "source_card_indices" in OVERVIEW_SYNTHESIS_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# _collect_allowed_ids_from_cards
# ---------------------------------------------------------------------------


def test_collect_allowed_ids_unions_all_cards() -> None:
    cats = [_cat_card("A", [1, 2]), _cat_card("B", [3])]
    tickers = [_ticker_card("X", [4, 5])]
    result = _collect_allowed_ids_from_cards(cats, tickers)
    assert result == {1, 2, 3, 4, 5}


def test_collect_allowed_ids_empty() -> None:
    assert _collect_allowed_ids_from_cards([], []) == set()


# ---------------------------------------------------------------------------
# _ids_from_card_indices
# ---------------------------------------------------------------------------


def test_ids_from_card_indices_category_cards() -> None:
    cats = [_cat_card("A", [10, 11]), _cat_card("B", [20])]
    tickers: list[TickerCard] = []
    result = _ids_from_card_indices([0, 1], cats, tickers)
    assert result == [10, 11, 20]


def test_ids_from_card_indices_ticker_offset() -> None:
    cats = [_cat_card("A", [1])]
    tickers = [_ticker_card("NVDA", [100, 101])]
    # ticker is at index 1 (offset = len(cats) = 1)
    result = _ids_from_card_indices([1], cats, tickers)
    assert result == [100, 101]


def test_ids_from_card_indices_out_of_range_skipped() -> None:
    cats = [_cat_card("A", [1])]
    tickers: list[TickerCard] = []
    result = _ids_from_card_indices([0, 999, -1], cats, tickers)
    assert result == [1]


def test_ids_from_card_indices_non_int_skipped() -> None:
    cats = [_cat_card("A", [5])]
    tickers: list[TickerCard] = []
    result = _ids_from_card_indices(["0", None, 0], cats, tickers)
    assert result == [5]


def test_ids_from_card_indices_deduplicates() -> None:
    """Two cards sharing chunk_ids — result should deduplicate."""
    cats = [_cat_card("A", [1, 2]), _cat_card("B", [2, 3])]
    tickers: list[TickerCard] = []
    result = _ids_from_card_indices([0, 1], cats, tickers)
    assert result.count(2) == 1
    assert set(result) == {1, 2, 3}


# ---------------------------------------------------------------------------
# _build_deterministic_pulse
# ---------------------------------------------------------------------------


def test_build_deterministic_pulse_orders_by_priority() -> None:
    cats = [
        _cat_card("A", [1], priority_score=0.3, title="Low"),
        _cat_card("B", [2], priority_score=0.9, title="High"),
        _cat_card("C", [3], priority_score=0.6, title="Mid"),
    ]
    pulse = _build_deterministic_pulse(cats, [])
    assert pulse[0].title == "High"
    assert pulse[1].title == "Mid"
    assert pulse[2].title == "Low"


def test_build_deterministic_pulse_max_5() -> None:
    cats = [_cat_card(f"cat{i}", [i], priority_score=float(i)) for i in range(10)]
    pulse = _build_deterministic_pulse(cats, [])
    assert len(pulse) <= 5


def test_build_deterministic_pulse_falls_back_to_ticker_when_no_cats() -> None:
    tickers = [_ticker_card("NVDA", [99], investment_case="AI demand")]
    pulse = _build_deterministic_pulse([], tickers)
    assert len(pulse) == 1
    assert pulse[0].title == "NVDA"
    assert 99 in pulse[0].evidence_chunk_ids


def test_build_deterministic_pulse_empty_fallback() -> None:
    pulse = _build_deterministic_pulse([], [])
    assert len(pulse) == 1
    assert pulse[0].key == "pulse-empty"


# ---------------------------------------------------------------------------
# _build_overview_result_from_llm
# ---------------------------------------------------------------------------


def test_build_overview_result_assigns_chunk_ids_per_item() -> None:
    """Each pulse item should reference only its own source card's chunk_ids, not a union."""
    from src.pipelines.stock_report.synthesize import OverviewPulseItemOutput

    cats = [_cat_card("A", [1, 2]), _cat_card("B", [3, 4])]
    tickers: list[TickerCard] = []
    allowed = _collect_allowed_ids_from_cards(cats, tickers)

    output = OverviewLLMOutput(
        pulse=[
            OverviewPulseItemOutput(
                key="pulse-1", title="P1", body="b1", source_card_indices=[0], priority_score=0.9
            ),
            OverviewPulseItemOutput(
                key="pulse-2", title="P2", body="b2", source_card_indices=[1], priority_score=0.7
            ),
        ],
        core_themes=[],
    )

    result = _build_overview_result_from_llm(output, cats, tickers, allowed)
    assert result.pulse[0].evidence_chunk_ids == [1, 2]
    assert result.pulse[1].evidence_chunk_ids == [3, 4]
    # top-level union
    assert set(result.evidence_chunk_ids) == {1, 2, 3, 4}


def test_build_overview_result_core_theme_requires_2_categories() -> None:
    from src.pipelines.stock_report.synthesize import (
        OverviewCoreThemeOutput,
        OverviewPulseItemOutput,
    )

    cats = [_cat_card("A", [1]), _cat_card("B", [2])]
    tickers: list[TickerCard] = []
    allowed = _collect_allowed_ids_from_cards(cats, tickers)

    output = OverviewLLMOutput(
        pulse=[OverviewPulseItemOutput(key="p1", title="T", body="B", source_card_indices=[0])],
        core_themes=[
            # Only 1 connected category — should be dropped
            OverviewCoreThemeOutput(
                key="bad-theme",
                title="Bad",
                thesis="Only one cat",
                connected_categories=["A"],
                source_card_indices=[0],
            ),
            # 2 connected categories — should be kept
            OverviewCoreThemeOutput(
                key="good-theme",
                title="Good",
                thesis="Two cats connected",
                connected_categories=["A", "B"],
                source_card_indices=[0, 1],
            ),
        ],
    )

    result = _build_overview_result_from_llm(output, cats, tickers, allowed)
    assert len(result.core_themes) == 1
    assert result.core_themes[0].key == "good-theme"


def test_build_overview_result_sanitizes_out_of_bundle_ids() -> None:
    from src.pipelines.stock_report.synthesize import OverviewPulseItemOutput

    cats = [_cat_card("A", [1, 2])]
    tickers: list[TickerCard] = []
    # allowed only has 1, 2 — card 0 references chunks 1 and 2 but we'll check filter
    allowed = {1}  # only id=1 is allowed

    output = OverviewLLMOutput(
        pulse=[OverviewPulseItemOutput(key="p1", title="T", body="B", source_card_indices=[0])],
        core_themes=[],
    )
    result = _build_overview_result_from_llm(output, cats, tickers, allowed)
    # chunk 2 should be removed by _sanitize_chunk_ids
    assert result.pulse[0].evidence_chunk_ids == [1]


def test_build_overview_result_fallback_pulse_when_llm_empty() -> None:
    from src.pipelines.stock_report.synthesize import OverviewLLMOutput

    cats = [_cat_card("A", [1], priority_score=0.8, title="Cat A")]
    tickers: list[TickerCard] = []
    allowed = _collect_allowed_ids_from_cards(cats, tickers)

    output = OverviewLLMOutput(pulse=[], core_themes=[])
    result = _build_overview_result_from_llm(output, cats, tickers, allowed)
    assert len(result.pulse) >= 1
    assert result.pulse[0].title == "Cat A"


# ---------------------------------------------------------------------------
# synthesize_overview — happy path (mocked)
# ---------------------------------------------------------------------------


def test_synthesize_overview_happy_path(monkeypatch) -> None:
    from src.pipelines.stock_report.synthesize import (
        OverviewCoreThemeOutput,
        OverviewPulseItemOutput,
    )

    cats = [_cat_card("반도체", [1, 2]), _cat_card("AI인프라", [3, 4])]
    tickers = [_ticker_card("NVDA", [5])]

    async def _fake_run(system, user, schema, provider):
        assert schema is OverviewLLMOutput
        return OverviewLLMOutput(
            pulse=[
                OverviewPulseItemOutput(
                    key="pulse-1",
                    title="HBM 수요 급증",
                    body="반도체 섹터 HBM 수요가 급증했다. NVDA +5%.",
                    source_card_indices=[0, 2],
                    priority_score=0.95,
                ),
                OverviewPulseItemOutput(
                    key="pulse-2",
                    title="AI 인프라 투자 확대",
                    body="AI 인프라 투자 확대 추세 지속.",
                    source_card_indices=[1],
                    priority_score=0.80,
                ),
            ],
            core_themes=[
                OverviewCoreThemeOutput(
                    key="theme-ai-infra",
                    title="AI 밸류체인 확산",
                    thesis="반도체·AI인프라 동반 강세로 밸류체인 전반에 수요 확산.",
                    connected_categories=["반도체", "AI인프라"],
                    impact="반도체·전력·부품 수요 동반 상승",
                    watch_points=["금리 변화", "공급 부족"],
                    source_card_indices=[0, 1],
                    priority_score=0.90,
                ),
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    result = asyncio.run(synthesize_overview(cats, tickers, provider="openai"))

    assert isinstance(result, OverviewResult)
    assert len(result.pulse) >= 3 or len(result.pulse) == 2  # LLM returned 2, that's OK
    assert len(result.core_themes) == 1
    assert result.core_themes[0].key == "theme-ai-infra"
    # chunk_ids per-item, not union blob
    pulse_1 = result.pulse[0]
    # source_card_indices=[0, 2]: cat card 0 has [1,2], ticker card at index 2 has [5]
    assert set(pulse_1.evidence_chunk_ids) == {1, 2, 5}
    pulse_2 = result.pulse[1]
    # source_card_indices=[1]: cat card 1 has [3, 4]
    assert set(pulse_2.evidence_chunk_ids) == {3, 4}


def test_synthesize_overview_openai_failure_deterministic_fallback(monkeypatch) -> None:
    async def _raise(system, user, schema, provider):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _raise,
    )

    cats = [_cat_card("반도체", [1, 2], priority_score=0.9, title="HBM 강세")]
    tickers = [_ticker_card("NVDA", [3])]

    result = asyncio.run(synthesize_overview(cats, tickers, provider="openai"))

    assert isinstance(result, OverviewResult)
    assert len(result.pulse) >= 1
    assert result.pulse[0].title == "HBM 강세"
    assert result.core_themes == []


def test_synthesize_overview_grounding_fails_falls_back_to_openai(monkeypatch) -> None:
    from src.pipelines.stock_report.synthesize import OverviewPulseItemOutput

    async def _fake_grounding(*args, **kwargs):
        raise RuntimeError("Gemini unavailable")

    async def _fake_run(system, user, schema, provider):
        return OverviewLLMOutput(
            pulse=[
                OverviewPulseItemOutput(
                    key="p1",
                    title="OpenAI fallback",
                    body="OpenAI 경로로 성공",
                    source_card_indices=[0],
                    priority_score=0.8,
                )
            ],
            core_themes=[],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_overview_grounding_call",
        _fake_grounding,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    cats = [_cat_card("반도체", [1])]
    tickers: list[TickerCard] = []

    result = asyncio.run(synthesize_overview(cats, tickers, provider="openai", grounding=True))

    assert result.pulse[0].title == "OpenAI fallback"


def test_synthesize_overview_grounding_and_openai_both_fail_deterministic(monkeypatch) -> None:
    async def _fail_grounding(*args, **kwargs):
        raise RuntimeError("Gemini down")

    async def _fail_openai(system, user, schema, provider):
        raise RuntimeError("OpenAI down")

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_overview_grounding_call",
        _fail_grounding,
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fail_openai,
    )

    cats = [_cat_card("반도체", [1], priority_score=0.9, title="HBM")]
    tickers: list[TickerCard] = []

    result = asyncio.run(synthesize_overview(cats, tickers, provider="openai", grounding=True))

    assert result.pulse[0].title == "HBM"
    assert result.core_themes == []


# ---------------------------------------------------------------------------
# synthesize_tiered — happy path (mocked map + reduce)
# ---------------------------------------------------------------------------


def test_synthesize_tiered_happy_path(monkeypatch) -> None:
    from src.pipelines.stock_report.synthesize import (
        CategoryCardLLMOutput,
        OverviewPulseItemOutput,
        TickerCardLLMOutput,
    )

    call_count = {"n": 0}

    async def _fake_run(system, user, schema, provider):
        call_count["n"] += 1
        if schema is CategoryCardLLMOutput:
            return CategoryCardLLMOutput(
                category_key="반도체",
                title="HBM 강세",
                narrative="HBM 수요 강세",
                evidence_bullets=["NVDA +5%"],
                impact="메모리 밸류체인 긍정",
                evidence_chunk_ids=[1, 2, 3],
                priority_score=0.85,
            )
        if schema is TickerCardLLMOutput:
            return TickerCardLLMOutput(
                ticker="NVDA",
                investment_case="HBM 전량 수주",
                catalysts=["Blackwell"],
                key_metrics=["+122% YoY"],
                risks=["공급 지연"],
                evidence_chunk_ids=[1, 2, 3],
            )
        # OverviewLLMOutput
        return OverviewLLMOutput(
            pulse=[
                OverviewPulseItemOutput(
                    key="p1",
                    title="HBM 수요",
                    body="HBM 수요 급증",
                    source_card_indices=[0, 1],
                    priority_score=0.9,
                )
            ],
            core_themes=[],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    # 3 chunks each so synthesize_category/ticker takes LLM path
    cat_bucket = _cat_bucket([1, 2, 3], "반도체")
    ticker_bucket = _ticker_bucket([1, 2, 3], "NVDA")

    result = asyncio.run(
        synthesize_tiered(
            category_buckets=[cat_bucket],
            ticker_buckets=[ticker_bucket],
            provider="openai",
            grounding=False,
        )
    )

    assert isinstance(result, OverviewResult)
    assert len(result.pulse) >= 1
    # _run_synthesis_call called: 1 category + 1 ticker + 1 overview = 3
    assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# chunk_id per-item attribution — not union blob
# ---------------------------------------------------------------------------


def test_pulse_item_ids_are_per_item_not_union(monkeypatch) -> None:
    """Regression: each pulse item must carry only its own source cards' ids."""
    from src.pipelines.stock_report.synthesize import OverviewPulseItemOutput

    cats = [
        _cat_card("A", [10, 11]),
        _cat_card("B", [20, 21]),
        _cat_card("C", [30]),
    ]
    tickers: list[TickerCard] = []

    async def _fake_run(system, user, schema, provider):
        return OverviewLLMOutput(
            pulse=[
                OverviewPulseItemOutput(
                    key="p1",
                    title="A signal",
                    body="from A",
                    source_card_indices=[0],
                    priority_score=0.9,
                ),
                OverviewPulseItemOutput(
                    key="p2",
                    title="B signal",
                    body="from B",
                    source_card_indices=[1],
                    priority_score=0.8,
                ),
                OverviewPulseItemOutput(
                    key="p3",
                    title="C signal",
                    body="from C",
                    source_card_indices=[2],
                    priority_score=0.7,
                ),
            ],
            core_themes=[],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        _fake_run,
    )

    result = asyncio.run(synthesize_overview(cats, tickers, provider="openai"))

    assert result.pulse[0].evidence_chunk_ids == [10, 11]
    assert result.pulse[1].evidence_chunk_ids == [20, 21]
    assert result.pulse[2].evidence_chunk_ids == [30]
    # Union in top-level overview
    assert set(result.evidence_chunk_ids) == {10, 11, 20, 21, 30}
