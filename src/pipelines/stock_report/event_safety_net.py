"""Deterministic safety net for high-impact corporate events.

Cross-date audits (2026-05-28, 2026-06-02) showed the per-category synthesis LLM
intermittently drops M&A / large capital-raise events during consolidation, even when
the source chunk sits well within the token budget. Prompt directives reduced but did
not eliminate this (LLM nondeterminism): the same directive surfaced some M&A events
while dropping others on both dates.

Because chunks already carry a structured ``event_type`` taxonomy, dropped high-impact
events can be detected deterministically and forced back into the category card — no
brittle keyword matching required. For a daily market briefing, omitting a major M&A or
capital event is a correctness defect, not acceptable curation; this module guarantees
those events survive.

Scope: applied only to the LLM-success category card, not ticker cards. The raw fallback
card already includes every chunk, so it needs no supplementing; ticker cards have no
evidence-bullet channel and any high-impact event already surfaces in its category card.

Buybacks are intentionally not a separate trigger: the canonical taxonomy folds them into
``자본조달`` (capital actions), which is already covered, so adding a non-canonical
``자사주매입`` member would be a silent no-op (the extraction LLM never emits it).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from src.pipelines.stock_report.retrieval import SameDayChunk
    from src.pipelines.stock_report.synthesize import CategorySummaryCard


logger = logging.getLogger(__name__)

# event_type values whose omission from a daily briefing is a defect rather than curation.
# Keyed off the structured field, not keywords. MUST be a subset of prompts.CANONICAL_EVENT_TYPES
# (guarded by test) so the extraction LLM is actually instructed to emit them.
HIGH_IMPACT_EVENT_TYPES: frozenset[str] = frozenset({"M&A", "자본조달"})

# A single category rarely carries more than a couple of dropped high-impact events.
# Cap supplements to bound clutter; truncation is logged (no silent caps).
_MAX_SUPPLEMENTS_PER_CATEGORY = 5


def _format_supplement(chunk: SameDayChunk) -> str:
    """Render one dropped high-impact chunk as a deterministic evidence bullet.

    The ``event_type`` prefix keeps the injection traceable in the rendered report and
    distinguishable from LLM-authored bullets during evaluation.
    """
    # event_type is guaranteed non-null here: callers only pass chunks that already
    # matched HIGH_IMPACT_EVENT_TYPES membership.
    event = chunk.event_type
    summary = chunk.canonical_summary.strip()
    fact = chunk.supporting_facts[0].strip() if chunk.supporting_facts else ""
    if fact and fact not in summary:
        return f"[{event}] {summary} ({fact})"
    return f"[{event}] {summary}"


def enforce_high_impact_event_coverage(
    card: CategorySummaryCard,
    bucket_chunks: list[SameDayChunk],
    *,
    max_supplements: int = _MAX_SUPPLEMENTS_PER_CATEGORY,
) -> CategorySummaryCard:
    """Force dropped high-impact-event chunks back into the category card.

    A chunk is a supplement candidate when its ``event_type`` is high-impact, its id was
    NOT cited by the LLM, and it carries a non-empty summary. Candidates are surfaced in
    ``priority_score`` order up to ``max_supplements``; each appends an evidence bullet
    and records its chunk id so downstream coverage/attribution counts it.

    Detection relies solely on citation (``id not in cited``) — deliberately biased
    toward inclusion. An entity-presence guard was considered and rejected: skipping a
    chunk because its ticker already appears elsewhere in the card risks re-dropping a
    genuine M&A whose entity was mentioned in an unrelated context. Rare duplication is
    the lesser evil versus a missed event.

    Mutates and returns ``card``.
    """
    cited = set(card.evidence_chunk_ids)
    candidates = [
        chunk
        for chunk in bucket_chunks
        if chunk.event_type in HIGH_IMPACT_EVENT_TYPES
        and chunk.id not in cited
        and chunk.canonical_summary.strip()
    ]
    if not candidates:
        return card

    candidates.sort(key=lambda chunk: (-chunk.priority_score, chunk.id))
    selected = candidates[:max_supplements]
    dropped_by_cap = len(candidates) - len(selected)

    for chunk in selected:
        card.evidence_bullets.append(_format_supplement(chunk))
        card.evidence_chunk_ids.append(chunk.id)

    logger.info(
        "event safety net: category=%s surfaced=%d dropped_by_cap=%d",
        card.category_key,
        len(selected),
        dropped_by_cap,
    )
    if dropped_by_cap:
        logger.warning(
            "event safety net cap hit: category=%s %d high-impact event(s) not surfaced "
            "(raise max_supplements if this recurs)",
            card.category_key,
            dropped_by_cap,
        )
    return card
