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
from src.pipelines.stock_report.event_safety_net import (
    HIGH_IMPACT_EVENT_TYPES,
    enforce_high_impact_event_coverage,
)
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
# T09-F: _sanitize_chunk_ids — unified chunk-id sanitization helper
# ---------------------------------------------------------------------------


def _sanitize_chunk_ids(ids: list[Any], allowed_bundle_ids: set[int]) -> list[int]:
    """Return only integer chunk ids that are present in allowed_bundle_ids.

    Single source of truth for chunk-id sanitization across the synthesis pipeline.
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


def _typed_evidence_texts(chunks: list[SameDayChunk], kind: str) -> list[str]:
    """Ordered, de-duplicated ``evidence_items.text`` for a given ``kind`` across chunks.

    The raw fallback otherwise ignores the typed evidence already attached to each chunk,
    which left thin (chunk < 3) ticker cards with no risk/metric axis (issue 4). Reusing the
    structured ``kind`` field surfaces those axes from real data — no invented placeholders.
    """
    seen: set[str] = set()
    result: list[str] = []
    for chunk in chunks:
        for item in chunk.evidence_items:
            if not isinstance(item, dict) or str(item.get("kind") or "").strip() != kind:
                continue
            text = str(item.get("text") or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


# Observed LLM typo in category synthesis output: '카테리' written for '카테고리' (issue 3).
# Prompt directives reduce but don't eliminate it (LLM nondeterminism), so we scrub it
# deterministically on synthesized prose. Safe as a substring replace: '카테리' is not a
# substring of the correct '카테고리', so correct text is never corrupted.
_REPORT_TYPO_FIXES = {"카테리": "카테고리"}


def _normalize_report_typos(text: str) -> str:
    """Fix known LLM typos in synthesized prose (see _REPORT_TYPO_FIXES)."""
    for wrong, right in _REPORT_TYPO_FIXES.items():
        text = text.replace(wrong, right)
    return text


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
        key_metrics=_typed_evidence_texts(bucket.chunks, "metric"),
        risks=_typed_evidence_texts(bucket.chunks, "risk"),
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
            title=_normalize_report_typos(output.title or bucket.category_key),
            narrative=_normalize_report_typos(output.narrative),
            evidence_bullets=[_normalize_report_typos(b) for b in output.evidence_bullets],
            impact=_normalize_report_typos(output.impact),
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
) -> OverviewResult:
    """Reduce per-category/per-ticker cards into an OverviewResult (Pulse + Core Themes).

    Fallback ladder:
    1. OpenAI structured call
    2. LLM failed → deterministic Pulse from top-priority cards, empty core_themes
    """
    allowed_ids = _collect_allowed_ids_from_cards(category_cards, ticker_cards)
    user_prompt = build_overview_prompt(category_cards, ticker_cards)

    try:
        output = await _run_synthesis_call(
            OVERVIEW_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            OverviewLLMOutput,
            provider,
        )
        assert isinstance(output, OverviewLLMOutput)
        return _build_overview_result_from_llm(output, category_cards, ticker_cards, allowed_ids)
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


# ---------------------------------------------------------------------------
# T09-G: synthesize_tiered — orchestrate map + reduce
# ---------------------------------------------------------------------------


_TIER_MAP_CONCURRENCY = 8
_TIER_FOCUS_TICKER_LIMIT = 10


def _is_ticker_like(ticker: str) -> bool:
    """A label that looks like a market symbol — a short ALL-CAPS ASCII code (TSLA, AVGO) or a
    numeric KR code (000660) — as opposed to a company name (Tesla, SpaceX, 테슬라)."""
    t = ticker.strip()
    if not t:
        return False
    if t.isdigit():
        return True
    return t.isascii() and t.isalpha() and t.isupper() and len(t) <= 5


def _dedupe_ticker_buckets(buckets: list[TickerBucket]) -> list[TickerBucket]:
    """Collapse name/symbol aliases that cover the exact same chunk set (issue 4a).

    An extraction chunk can be tagged with both a company name ("Tesla", "SpaceX") and its
    symbol ("TSLA"); each tag spawns a separate TickerBucket over the SAME chunks, which then
    renders as duplicate Focus Ticker cards. We only consider buckets whose chunk-id sets are
    identical, and only merge when exactly ONE of them is ticker-like: the names collapse into
    that canonical symbol. Two+ ticker-like labels over the same chunks (e.g. an "AMD vs NVDA"
    comparison piece) are kept separate — we must not silently merge two genuinely distinct
    symbols. Groups with no symbol stay separate too (conservative: avoids merging unrelated
    names). Original order is preserved for downstream determinism.
    """
    groups: dict[frozenset[int], list[tuple[int, TickerBucket]]] = {}
    order: list[frozenset[int]] = []
    for idx, bucket in enumerate(buckets):
        key = frozenset(chunk.id for chunk in bucket.chunks)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((idx, bucket))

    kept: list[tuple[int, TickerBucket]] = []
    for key in order:
        members = groups[key]
        ticker_like = [m for m in members if _is_ticker_like(m[1].ticker)]
        if len(members) > 1 and len(ticker_like) == 1:
            kept.append(ticker_like[0])  # names → single canonical symbol
        else:
            kept.extend(members)
    kept.sort(key=lambda m: m[0])
    return [bucket for _, bucket in kept]


# Issue 1: categories below this chunk count already take the deterministic raw-fallback path
# (see _CATEGORY_RAW_FALLBACK_THRESHOLD) — no LLM narrative/impact — so rendering each as its own
# card yields empty Impact and bare "ticker: -" stocks. We consolidate them into one compact
# '기타 단신' item instead of dropping them, keeping headline coverage without the noise.
MINOR_CATEGORY_ITEM_KEY = "__minor_briefs__"
_MINOR_BRIEF_MAX_ITEMS = 12


def _partition_category_buckets(
    buckets: list[CategoryBucket],
    *,
    threshold: int = _CATEGORY_RAW_FALLBACK_THRESHOLD,
) -> tuple[list[CategoryBucket], list[CategoryBucket]]:
    """Split category buckets into (major, minor) by chunk count.

    minor = chunk_count < threshold, deliberately matching the raw-fallback cutoff so the demoted
    set is exactly the categories that would otherwise render as low-fidelity raw cards.
    """
    major = [b for b in buckets if len(b.chunks) >= threshold]
    minor = [b for b in buckets if len(b.chunks) < threshold]
    return major, minor


def _format_minor_brief(chunk: SameDayChunk, category_key: str) -> str:
    summary = chunk.canonical_summary.strip()
    label = f"{category_key}: {summary}" if summary else category_key
    # Flag high-impact events (M&A/자본조달) so the cap can never bury a market-moving event.
    if chunk.event_type in HIGH_IMPACT_EVENT_TYPES:
        return f"[{chunk.event_type}] {label}"
    return label


def _build_minor_categories_item(
    minor_buckets: list[CategoryBucket],
    *,
    max_items: int = _MINOR_BRIEF_MAX_ITEMS,
) -> ReportSectionItem | None:
    """Consolidate low-signal categories into a single '기타 단신' ReportSectionItem.

    Each surviving chunk becomes one compact '카테고리: 요약' bullet. High-impact events are
    flagged and ordered first so the ``max_items`` cap never silently buries an M&A / capital
    action; any overflow is logged and shown as a trailing '… 외 N건 생략' bullet (no silent
    truncation). Returns None when there is nothing to surface.
    """
    candidates: list[tuple[bool, float, int, SameDayChunk, str]] = []
    for bucket in minor_buckets:
        for chunk in bucket.chunks:
            if not chunk.canonical_summary.strip():
                continue
            high = chunk.event_type in HIGH_IMPACT_EVENT_TYPES
            candidates.append((high, chunk.priority_score, chunk.id, chunk, bucket.category_key))
    if not candidates:
        return None

    # high-impact first, then priority desc, then id for determinism
    candidates.sort(key=lambda c: (not c[0], -c[1], c[2]))
    shown = candidates[:max_items]
    dropped = len(candidates) - len(shown)

    bullets = [_format_minor_brief(chunk, category_key) for _, _, _, chunk, category_key in shown]
    chunk_ids = [chunk.id for _, _, _, chunk, _ in shown]
    if dropped > 0:
        bullets.append(f"… 외 {dropped}건 생략")
        logger.info("minor categories brief capped: shown=%d dropped=%d", len(shown), dropped)

    return ReportSectionItem(
        key=MINOR_CATEGORY_ITEM_KEY,
        title="기타 단신",
        body="",
        evidence_bullets=bullets,
        evidence_chunk_ids=chunk_ids,
    )


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
    minor_item: ReportSectionItem | None = None,
) -> StockReportArtifact:
    """Adapt T09-F/G cards + reduce output into the StockReportArtifact contract.

    ``minor_item`` (issue 1) is the consolidated '기타 단신' card for low-signal categories; when
    present it is appended after the full category cards so it shares the category 출처 pipeline.
    """
    chunk_index = _index_chunks(bundle)
    category_summaries = [_card_to_category_item(c) for c in category_cards]
    if minor_item is not None:
        category_summaries.append(minor_item)
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
) -> StockReportArtifact:
    """Full map-reduce: per-category + top-N ticker map → reduce → StockReportArtifact.

    Category coverage is guaranteed by iterating bundle.category_buckets in code.
    Falls back to the deterministic artifact only if the whole pipeline raises or
    yields nothing.
    """
    # Demote low-signal (chunk<3) categories to a single '기타 단신' card (issue 1): they only
    # ever take the raw-fallback path, so a full card per category is noise. Major categories
    # still get full per-category LLM synthesis.
    major_buckets, minor_buckets = _partition_category_buckets(bundle.category_buckets)
    # Collapse name/symbol alias buckets (Tesla/SpaceX → TSLA) before picking the top-N so the
    # limit and the rendered Focus Tickers are over distinct entities (issue 4a).
    deduped_ticker_buckets = _dedupe_ticker_buckets(bundle.focus_ticker_buckets)
    ticker_buckets = sorted(deduped_ticker_buckets, key=lambda b: len(b.chunks), reverse=True)[
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
        category_cards = list(await asyncio.gather(*[_cat(b) for b in major_buckets]))
        ticker_cards = list(await asyncio.gather(*[_tic(b) for b in ticker_buckets]))
        overview = await synthesize_overview(category_cards, ticker_cards, provider=provider)
        minor_item = _build_minor_categories_item(minor_buckets)
        artifact = _assemble_tiered_artifact(
            bundle, category_cards, ticker_cards, overview, minor_item
        )
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
) -> StockReportArtifact:
    """Sync entry point for the tiered pipeline (wraps asyncio.run)."""
    return asyncio.run(synthesize_tiered(bundle, provider=provider))


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
