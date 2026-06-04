from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.stock_report.config import (
    SEMANTIC_EXTRACTION_MAX_RETRIES,
    SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    get_report_synthesis_llm_config,
)
from src.pipelines.stock_report.event_safety_net import enforce_high_impact_event_coverage
from src.pipelines.stock_report.prompts import (
    CATEGORY_SYNTHESIS_SYSTEM_PROMPT,
    OVERVIEW_SYNTHESIS_SYSTEM_PROMPT,
    TICKER_SYNTHESIS_SYSTEM_PROMPT,
    build_category_synthesis_prompt,
    build_overview_prompt,
    build_ticker_synthesis_prompt,
)
from src.pipelines.stock_report.retrieval import (
    CategoryBucket,
    SameDayBundle,
    SameDayChunk,
    ThemeBucket,
    TickerBucket,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# T09-E: Evidence bundle contract (Phase 2/3 seam)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EvidenceItem:
    """Single chunk projected into the evidence bundle contract."""

    chunk_id: int
    summary: str
    supporting_facts: list[str]
    # Typed evidence dicts carry `kind` (metric/fact/thesis/risk/market_context/author_comment)
    # and `text`.  Full list, never truncated, so T09-F per-category callers can surface kind
    # labels without reaching back to raw SameDayChunk.
    evidence_items: list[dict[str, Any]]
    source: str  # "{channel_name}#{channel_message_id}"
    tickers: list[str]
    message_type: str


@dataclass(slots=True)
class CategorySummaryCard:
    category_key: str
    title: str
    narrative: str
    evidence_bullets: list[str]
    impact: str
    related_stocks: list[dict[str, str | None]]
    evidence_chunk_ids: list[int]
    priority_score: float = 0.0


@dataclass(slots=True)
class TickerCard:
    ticker: str
    investment_case: str
    catalysts: list[str]
    key_metrics: list[str]
    risks: list[str]
    evidence_chunk_ids: list[int]


@dataclass(slots=True)
class OverviewResult:
    pulse: list[ReportSectionItem]
    core_themes: list[ReportSectionItem]
    evidence_chunk_ids: list[int]


def _make_source(chunk: SameDayChunk) -> str:
    channel = chunk.channel_name or chunk.channel_key or "unknown"
    msg_id = chunk.channel_message_id or ""
    return f"{channel}#{msg_id}"


def build_category_evidence(bucket: CategoryBucket) -> list[EvidenceItem]:
    """Project all same-day chunks in a CategoryBucket into EvidenceItems.

    supporting_facts and evidence_items are never truncated — full lists are
    preserved so that per-category synthesis callers can make their own
    token-budget decisions and surface typed evidence (kind labels) without
    reaching back to raw SameDayChunk.
    """
    return [
        EvidenceItem(
            chunk_id=chunk.id,
            summary=chunk.canonical_summary,
            supporting_facts=list(chunk.supporting_facts),
            evidence_items=list(chunk.evidence_items),
            source=_make_source(chunk),
            tickers=list(chunk.ticker_tags),
            message_type=chunk.message_type,
        )
        for chunk in bucket.chunks
    ]


def build_ticker_evidence(bucket: TickerBucket) -> list[EvidenceItem]:
    """Project all same-day chunks in a TickerBucket into EvidenceItems.

    supporting_facts and evidence_items are never truncated.
    """
    return [
        EvidenceItem(
            chunk_id=chunk.id,
            summary=chunk.canonical_summary,
            supporting_facts=list(chunk.supporting_facts),
            evidence_items=list(chunk.evidence_items),
            source=_make_source(chunk),
            tickers=list(chunk.ticker_tags),
            message_type=chunk.message_type,
        )
        for chunk in bucket.chunks
    ]


# ---------------------------------------------------------------------------
# T09-F: _sanitize_chunk_ids — unified helper (google_grounding imports from here)
# ---------------------------------------------------------------------------


def _sanitize_chunk_ids(ids: list[Any], allowed_bundle_ids: set[int]) -> list[int]:
    """Return only integer chunk ids that are present in allowed_bundle_ids.

    This is the single source of truth for chunk-id sanitization.  google_grounding.py
    should import this rather than maintaining a duplicate.
    """
    result: list[int] = []
    for v in ids:
        if isinstance(v, int) and v in allowed_bundle_ids:
            result.append(v)
    return result


# ---------------------------------------------------------------------------
# T09-F: per-category / per-ticker LLM output schemas
# ---------------------------------------------------------------------------


class RelatedStockLLM(BaseModel):
    # Nested model (not dict[str, Any]) so OpenAI strict structured-output accepts the schema.
    name: str = ""
    ticker: str | None = None
    catalyst: str = ""


class CategoryCardLLMOutput(BaseModel):
    category_key: str | None = None
    title: str = ""
    narrative: str = ""
    evidence_bullets: list[str] = Field(default_factory=list)
    impact: str = ""
    related_stocks: list[RelatedStockLLM] = Field(default_factory=list)
    evidence_chunk_ids: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class TickerCardLLMOutput(BaseModel):
    ticker: str = ""
    investment_case: str = ""
    catalysts: list[str] = Field(default_factory=list)
    key_metrics: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# T09-F: _run_synthesis_call shared helper
# ---------------------------------------------------------------------------


async def _run_synthesis_call(
    system: str,
    user: str,
    schema: type[BaseModel],
    provider: str,
) -> BaseModel:
    """Shared helper: wraps invoke_llm_with_retry for per-category / per-ticker calls."""
    llm_config = get_report_synthesis_llm_config(provider)
    llm = llm_config.create_llm()
    messages = llm_config.build_messages(system, user)
    config = {
        "run_name": f"StockReport Per-Category Synthesis ({provider})",
        "tags": ["stock_report", "daily_v2", "per_category_synthesis", f"provider:{provider}"],
        "metadata": {
            "stage": "per_category_synthesis",
            "provider": provider,
            "model": llm_config.model,
            "prompt_chars": len(user),
        },
    }
    return await invoke_llm_with_retry(
        llm,
        schema,
        messages,
        config,
        max_retries=SEMANTIC_EXTRACTION_MAX_RETRIES,
        timeout_seconds=SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# T09-F: raw (deterministic) fallback card builders
# ---------------------------------------------------------------------------


def _render_raw_category_card(bucket: CategoryBucket) -> CategorySummaryCard:
    """Deterministic fallback: build a CategorySummaryCard directly from the bucket."""
    summaries = [
        chunk.canonical_summary.strip()
        for chunk in bucket.chunks
        if chunk.canonical_summary.strip()
    ]
    narrative = " / ".join(summaries) if summaries else "요약 가능한 당일 근거가 없습니다."
    evidence_bullets = [fact for chunk in bucket.chunks for fact in chunk.supporting_facts]
    related_stocks: list[dict[str, str | None]] = []
    seen_tickers: set[str] = set()
    for chunk in bucket.chunks:
        for ticker in chunk.ticker_tags:
            if ticker and ticker not in seen_tickers:
                related_stocks.append({"name": ticker, "ticker": ticker, "catalyst": ""})
                seen_tickers.add(ticker)
    return CategorySummaryCard(
        category_key=bucket.category_key,
        title=bucket.category_key,
        narrative=narrative,
        evidence_bullets=evidence_bullets,
        impact="",
        related_stocks=related_stocks,
        evidence_chunk_ids=[chunk.id for chunk in bucket.chunks],
        priority_score=0.0,
    )


def _render_raw_ticker_card(bucket: TickerBucket) -> TickerCard:
    """Deterministic fallback: build a TickerCard directly from the bucket."""
    summaries = [
        chunk.canonical_summary.strip()
        for chunk in bucket.chunks
        if chunk.canonical_summary.strip()
    ]
    investment_case = " / ".join(summaries) if summaries else "요약 가능한 당일 근거가 없습니다."
    catalysts = [fact for chunk in bucket.chunks for fact in chunk.supporting_facts]
    return TickerCard(
        ticker=bucket.ticker,
        investment_case=investment_case,
        catalysts=catalysts,
        key_metrics=[],
        risks=[],
        evidence_chunk_ids=[chunk.id for chunk in bucket.chunks],
    )


# ---------------------------------------------------------------------------
# T09-F: synthesize_category / synthesize_ticker
# ---------------------------------------------------------------------------

_CATEGORY_RAW_FALLBACK_THRESHOLD = 3


async def synthesize_category(
    bucket: CategoryBucket,
    *,
    provider: str = "openai",
) -> CategorySummaryCard:
    """Synthesize a single CategoryBucket into a CategorySummaryCard.

    Hybrid strategy:
    - chunk_count < 3 → deterministic raw fallback (no LLM call)
    - LLM call fails (retries exhausted) → same raw fallback
    """
    if len(bucket.chunks) < _CATEGORY_RAW_FALLBACK_THRESHOLD:
        return _render_raw_category_card(bucket)

    allowed_ids = {chunk.id for chunk in bucket.chunks}
    user_prompt = build_category_synthesis_prompt(bucket)
    try:
        output = await _run_synthesis_call(
            CATEGORY_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            CategoryCardLLMOutput,
            provider,
        )
        assert isinstance(output, CategoryCardLLMOutput)
        clean_ids = _sanitize_chunk_ids(output.evidence_chunk_ids, allowed_ids)
        related_stocks: list[dict[str, str | None]] = [
            {
                "name": stock.name,
                "ticker": stock.ticker or None,
                "catalyst": stock.catalyst,
            }
            for stock in output.related_stocks
        ]
        card = CategorySummaryCard(
            category_key=output.category_key or bucket.category_key,
            title=output.title or bucket.category_key,
            narrative=output.narrative,
            evidence_bullets=output.evidence_bullets,
            impact=output.impact,
            related_stocks=related_stocks,
            evidence_chunk_ids=clean_ids,
            priority_score=output.priority_score,
        )
        return enforce_high_impact_event_coverage(card, bucket.chunks)
    except Exception:
        logger.warning(
            "synthesize_category LLM failed, using raw fallback: category=%s provider=%s",
            bucket.category_key,
            provider,
            exc_info=True,
        )
        return _render_raw_category_card(bucket)


async def synthesize_ticker(
    bucket: TickerBucket,
    *,
    provider: str = "openai",
) -> TickerCard:
    """Synthesize a single TickerBucket into a TickerCard.

    Hybrid strategy:
    - chunk_count < 3 → deterministic raw fallback (no LLM call)
    - LLM call fails (retries exhausted) → same raw fallback
    """
    if len(bucket.chunks) < _CATEGORY_RAW_FALLBACK_THRESHOLD:
        return _render_raw_ticker_card(bucket)

    allowed_ids = {chunk.id for chunk in bucket.chunks}
    user_prompt = build_ticker_synthesis_prompt(bucket)
    try:
        output = await _run_synthesis_call(
            TICKER_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            TickerCardLLMOutput,
            provider,
        )
        assert isinstance(output, TickerCardLLMOutput)
        clean_ids = _sanitize_chunk_ids(output.evidence_chunk_ids, allowed_ids)
        return TickerCard(
            ticker=output.ticker or bucket.ticker,
            investment_case=output.investment_case,
            catalysts=output.catalysts,
            key_metrics=output.key_metrics,
            risks=output.risks,
            evidence_chunk_ids=clean_ids,
        )
    except Exception:
        logger.warning(
            "synthesize_ticker LLM failed, using raw fallback: ticker=%s provider=%s",
            bucket.ticker,
            provider,
            exc_info=True,
        )
        return _render_raw_ticker_card(bucket)


# ---------------------------------------------------------------------------
# T09-G: overview (reduce) LLM output schemas
# ---------------------------------------------------------------------------


class OverviewPulseItemOutput(BaseModel):
    key: str = ""
    title: str = ""
    body: str = ""
    source_card_indices: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class OverviewCoreThemeOutput(BaseModel):
    key: str = ""
    title: str = ""
    thesis: str = ""
    connected_categories: list[str] = Field(default_factory=list)
    impact: str = ""
    watch_points: list[str] = Field(default_factory=list)
    source_card_indices: list[int] = Field(default_factory=list)
    priority_score: float = 0.0


class OverviewLLMOutput(BaseModel):
    pulse: list[OverviewPulseItemOutput] = Field(default_factory=list)
    core_themes: list[OverviewCoreThemeOutput] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# T09-G: chunk_id attribution helpers for reduce step
# ---------------------------------------------------------------------------


def _collect_allowed_ids_from_cards(
    category_cards: list[CategorySummaryCard],
    ticker_cards: list[TickerCard],
) -> set[int]:
    allowed: set[int] = set()
    for card in category_cards:
        allowed.update(card.evidence_chunk_ids)
    for card in ticker_cards:
        allowed.update(card.evidence_chunk_ids)
    return allowed


def _ids_from_card_indices(
    indices: list[Any],
    category_cards: list[CategorySummaryCard],
    ticker_cards: list[TickerCard],
) -> list[int]:
    """Collect evidence_chunk_ids from referenced cards, preserve per-item attribution.

    indices are 0-based offsets into [category_cards..., ticker_cards...].
    Returns deduplicated chunk ids from those cards only.
    """
    all_cards: list[CategorySummaryCard | TickerCard] = [*category_cards, *ticker_cards]
    result: list[int] = []
    seen: set[int] = set()
    for raw_idx in indices:
        if not isinstance(raw_idx, int):
            continue
        if raw_idx < 0 or raw_idx >= len(all_cards):
            continue
        card = all_cards[raw_idx]
        for cid in card.evidence_chunk_ids:
            if cid not in seen:
                seen.add(cid)
                result.append(cid)
    return result


def _build_deterministic_pulse(
    category_cards: list[CategorySummaryCard],
    ticker_cards: list[TickerCard],
) -> list[ReportSectionItem]:
    """Deterministic Pulse fallback: top-5 category cards by priority_score."""
    sorted_cats = sorted(category_cards, key=lambda c: -c.priority_score)
    items: list[ReportSectionItem] = []
    for idx, card in enumerate(sorted_cats[:5]):
        items.append(
            ReportSectionItem(
                key=f"pulse-{idx + 1}",
                title=card.title,
                body=card.narrative,
                evidence_chunk_ids=list(card.evidence_chunk_ids),
            )
        )
    if not items and ticker_cards:
        card = ticker_cards[0]
        items.append(
            ReportSectionItem(
                key="pulse-1",
                title=card.ticker,
                body=card.investment_case,
                evidence_chunk_ids=list(card.evidence_chunk_ids),
            )
        )
    if not items:
        items.append(
            ReportSectionItem(
                key="pulse-empty",
                title="데일리 요약",
                body="당일 리포트에 반영할 카드가 없습니다.",
                evidence_chunk_ids=[],
            )
        )
    return items


# ---------------------------------------------------------------------------
# T09-G: synthesize_overview
# ---------------------------------------------------------------------------


async def synthesize_overview(
    category_cards: list[CategorySummaryCard],
    ticker_cards: list[TickerCard],
    *,
    provider: str = "openai",
    grounding: bool = False,
) -> OverviewResult:
    """Reduce per-category/per-ticker cards into an OverviewResult (Pulse + Core Themes).

    Fallback ladder:
    1. grounding=True  → Google Grounding Gemini call
    2. grounding=False (or grounding failed) → OpenAI structured call
    3. LLM entirely failed → deterministic Pulse from top-priority cards, empty core_themes
    """
    allowed_ids = _collect_allowed_ids_from_cards(category_cards, ticker_cards)
    user_prompt = build_overview_prompt(category_cards, ticker_cards)

    async def _call_openai() -> OverviewResult:
        output = await _run_synthesis_call(
            OVERVIEW_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            OverviewLLMOutput,
            provider,
        )
        assert isinstance(output, OverviewLLMOutput)
        return _build_overview_result_from_llm(output, category_cards, ticker_cards, allowed_ids)

    async def _call_grounding() -> OverviewResult:
        return await _run_overview_grounding_call(
            user_prompt, category_cards, ticker_cards, allowed_ids
        )

    if grounding:
        try:
            return await _call_grounding()
        except Exception:
            logger.warning(
                "synthesize_overview grounding call failed, falling back to openai",
                exc_info=True,
            )

    try:
        return await _call_openai()
    except Exception:
        logger.warning(
            "synthesize_overview openai call failed, using deterministic fallback",
            exc_info=True,
        )

    pulse = _build_deterministic_pulse(category_cards, ticker_cards)
    all_ids = list(allowed_ids)
    return OverviewResult(pulse=pulse, core_themes=[], evidence_chunk_ids=all_ids)


def _build_overview_result_from_llm(
    output: OverviewLLMOutput,
    category_cards: list[CategorySummaryCard],
    ticker_cards: list[TickerCard],
    allowed_ids: set[int],
) -> OverviewResult:
    pulse: list[ReportSectionItem] = []
    for idx, item in enumerate(output.pulse[:5]):
        item_ids = _ids_from_card_indices(item.source_card_indices, category_cards, ticker_cards)
        clean_ids = _sanitize_chunk_ids(item_ids, allowed_ids)
        pulse.append(
            ReportSectionItem(
                key=item.key or f"pulse-{idx + 1}",
                title=item.title,
                body=item.body,
                evidence_chunk_ids=clean_ids,
                priority_score=item.priority_score,
            )
        )

    core_themes: list[ReportSectionItem] = []
    for item in output.core_themes:
        if len(set(item.connected_categories)) < 2:
            continue
        item_ids = _ids_from_card_indices(item.source_card_indices, category_cards, ticker_cards)
        clean_ids = _sanitize_chunk_ids(item_ids, allowed_ids)
        core_themes.append(
            ReportSectionItem(
                key=item.key or item.title,
                title=item.title,
                body=item.thesis,
                thesis=item.thesis,
                impact=item.impact,
                watch_points=item.watch_points,
                related_categories=list(item.connected_categories),
                evidence_chunk_ids=clean_ids,
                priority_score=item.priority_score,
            )
        )

    if not pulse:
        pulse = _build_deterministic_pulse(category_cards, ticker_cards)

    all_item_ids: list[int] = []
    seen: set[int] = set()
    for item in pulse + core_themes:
        for cid in item.evidence_chunk_ids:
            if cid not in seen:
                seen.add(cid)
                all_item_ids.append(cid)

    return OverviewResult(
        pulse=pulse,
        core_themes=core_themes,
        evidence_chunk_ids=all_item_ids,
    )


async def _run_overview_grounding_call(
    user_prompt: str,
    category_cards: list[CategorySummaryCard],
    ticker_cards: list[TickerCard],
    allowed_ids: set[int],
) -> OverviewResult:
    """Attempt a Google Grounding Gemini call for the reduce step.

    Raises on failure so synthesize_overview can fall back to openai.
    """
    import os

    try:
        from google import genai
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
    except ImportError as exc:
        raise ImportError(
            "google-genai is required for grounding. Run: uv add google-genai"
        ) from exc

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is required for grounding")

    model = os.getenv("STOCK_REPORT_GOOGLE_MODEL") or "gemini-2.5-flash"
    client = genai.Client(api_key=api_key)
    gen_config = GenerateContentConfig(
        system_instruction=OVERVIEW_SYNTHESIS_SYSTEM_PROMPT,
        tools=[Tool(google_search=GoogleSearch())],
        temperature=0.1,
    )

    full_prompt = user_prompt
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=model,
            contents=full_prompt,
            config=gen_config,
        ),
    )
    raw_text = response.text or ""
    import json as _json

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        start = next((i + 1 for i, line in enumerate(lines) if line.startswith("```")), 1)
        end = next(
            (i for i in range(len(lines) - 1, start, -1) if lines[i].startswith("```")),
            len(lines),
        )
        cleaned = "\n".join(lines[start:end])
    parsed = _json.loads(cleaned)
    output = OverviewLLMOutput.model_validate(parsed)
    return _build_overview_result_from_llm(output, category_cards, ticker_cards, allowed_ids)


# ---------------------------------------------------------------------------
# T09-G: synthesize_tiered — orchestrate map + reduce
# ---------------------------------------------------------------------------


_TIER_MAP_CONCURRENCY = 8
_TIER_FOCUS_TICKER_LIMIT = 10


def _card_to_category_item(card: CategorySummaryCard) -> ReportSectionItem:
    return ReportSectionItem(
        key=card.category_key,
        title=card.title or card.category_key,
        body=card.narrative,
        evidence_bullets=list(card.evidence_bullets),
        impact=card.impact or None,
        related_stocks=list(card.related_stocks),
        evidence_chunk_ids=list(card.evidence_chunk_ids),
        priority_score=card.priority_score,
    )


def _card_to_ticker_item(card: TickerCard) -> ReportSectionItem:
    return ReportSectionItem(
        key=card.ticker,
        title=card.ticker,
        body=card.investment_case,
        investment_case=card.investment_case,
        catalysts=list(card.catalysts),
        key_metrics=list(card.key_metrics),
        risks_or_watch_points=list(card.risks),
        evidence_chunk_ids=list(card.evidence_chunk_ids),
    )


def _refs_for_items(
    section_key: str,
    items: list[ReportSectionItem],
    chunk_index: dict[int, SameDayChunk],
) -> list[ReportEvidenceRef]:
    refs: list[ReportEvidenceRef] = []
    for item in items:
        chunks = [chunk_index[cid] for cid in item.evidence_chunk_ids if cid in chunk_index]
        if not chunks:
            continue
        refs.extend(_evidence_refs(section_key=section_key, item_key=item.key, chunks=chunks))
    return refs


def _assemble_tiered_artifact(
    bundle: SameDayBundle,
    category_cards: list[CategorySummaryCard],
    ticker_cards: list[TickerCard],
    overview: OverviewResult,
) -> StockReportArtifact:
    """Adapt T09-F/G cards + reduce output into the StockReportArtifact contract."""
    chunk_index = _index_chunks(bundle)
    category_summaries = [_card_to_category_item(c) for c in category_cards]
    focus_tickers = [_card_to_ticker_item(c) for c in ticker_cards]
    pulse = list(overview.pulse)
    core_themes = list(overview.core_themes)
    low_confidence_notes = [
        chunk.canonical_summary for chunk in bundle.low_confidence_chunks if chunk.canonical_summary
    ]

    evidence_refs: list[ReportEvidenceRef] = []
    evidence_refs.extend(_refs_for_items("pulse", pulse, chunk_index))
    evidence_refs.extend(_refs_for_items("category_summaries", category_summaries, chunk_index))
    evidence_refs.extend(_refs_for_items("core_themes", core_themes, chunk_index))
    evidence_refs.extend(_refs_for_items("focus_tickers", focus_tickers, chunk_index))

    return StockReportArtifact(
        report_date=bundle.report_date,
        pulse=pulse,
        category_summaries=category_summaries,
        core_themes=core_themes,
        focus_tickers=focus_tickers,
        low_confidence_notes=low_confidence_notes,
        evidence_refs=evidence_refs,
    )


async def synthesize_tiered(
    bundle: SameDayBundle,
    *,
    provider: str = "openai",
    grounding: bool = False,
) -> StockReportArtifact:
    """Full map-reduce: per-category + top-N ticker map → reduce → StockReportArtifact.

    Category coverage is guaranteed by iterating bundle.category_buckets in code.
    Falls back to the deterministic artifact only if the whole pipeline raises or
    yields nothing.
    """
    category_buckets = list(bundle.category_buckets)
    ticker_buckets = sorted(bundle.focus_ticker_buckets, key=lambda b: len(b.chunks), reverse=True)[
        :_TIER_FOCUS_TICKER_LIMIT
    ]

    sem = asyncio.Semaphore(_TIER_MAP_CONCURRENCY)

    async def _cat(b: CategoryBucket) -> CategorySummaryCard:
        async with sem:
            return await synthesize_category(b, provider=provider)

    async def _tic(b: TickerBucket) -> TickerCard:
        async with sem:
            return await synthesize_ticker(b, provider=provider)

    try:
        category_cards = list(await asyncio.gather(*[_cat(b) for b in category_buckets]))
        ticker_cards = list(await asyncio.gather(*[_tic(b) for b in ticker_buckets]))
        overview = await synthesize_overview(
            category_cards, ticker_cards, provider=provider, grounding=grounding
        )
        artifact = _assemble_tiered_artifact(bundle, category_cards, ticker_cards, overview)
        if artifact.category_summaries or artifact.focus_tickers or artifact.core_themes:
            return artifact
        logger.warning(
            "tiered synthesis empty, fallback to deterministic: date=%s", bundle.report_date
        )
    except Exception:
        logger.exception(
            "tiered synthesis failed, fallback to deterministic: date=%s", bundle.report_date
        )
    return _build_deterministic_artifact(bundle)


def synthesize_daily(
    bundle: SameDayBundle,
    *,
    provider: str = "openai",
    grounding: bool = False,
) -> StockReportArtifact:
    """Sync entry point for the tiered pipeline (wraps asyncio.run)."""
    return asyncio.run(synthesize_tiered(bundle, provider=provider, grounding=grounding))


# ---------------------------------------------------------------------------
# Legacy structures (kept until T09-H)
# ---------------------------------------------------------------------------


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
