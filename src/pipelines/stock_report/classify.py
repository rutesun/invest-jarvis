from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.stock_report.config import (
    SEMANTIC_EXTRACTION_MAX_CONCURRENCY,
    SEMANTIC_EXTRACTION_MAX_RETRIES,
    SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    get_semantic_extraction_llm_config,
)
from src.pipelines.stock_report.models import (
    ClassifiedMessage,
    NormalizedMessage,
    SemanticExtractionDraft,
    SemanticUnitDraft,
)
from src.pipelines.stock_report.prompts import (
    SEMANTIC_EXTRACTION_SYSTEM_PROMPT,
    build_semantic_extraction_user_prompt,
)
from src.pipelines.stock_report.taxonomy import (
    TaxonomyRegistry,
    build_match_dictionary,
    render_taxonomy_outline,
)


logger = logging.getLogger(__name__)
MULTISPACE_PATTERN = __import__("re").compile(r"\s+")


def _dedupe_preserve_order(values: list[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
        if limit is not None and len(result) >= limit:
            break
    return result


def _normalize_category_key(value: str | None, category_map: dict[str, str]) -> str:
    if not value:
        return "unclassified"
    return category_map.get(value.strip().lower(), "unclassified")


def _normalize_theme(
    value: str | None,
    theme_map: dict[str, tuple[str, str]],
) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    match = theme_map.get(value.strip().lower())
    if not match:
        return None, None
    return match


def _fallback_canonical_summary(clean_text: str) -> str:
    if not clean_text:
        return ""
    line = clean_text.split("\n", 1)[0]
    line = MULTISPACE_PATTERN.sub(" ", line).strip()
    return line[:80].rstrip()


def _build_fallback_message(row: NormalizedMessage) -> ClassifiedMessage | None:
    canonical_summary = _fallback_canonical_summary(row.clean_text)
    if not canonical_summary:
        return None

    return ClassifiedMessage(
        telegram_message_id=row.telegram_message_id,
        source_date=row.source_date,
        channel_key=row.channel_key,
        source_channel_key=row.source_channel_key,
        processing_mode=row.processing_mode,
        structure_type="single_topic_deep",
        unit_index=0,
        message_type="signal",
        category_key="unclassified",
        main_theme=None,
        sub_themes=[],
        ticker_tags=[],
        canonical_summary=canonical_summary,
        supporting_facts=[],
    )


def _normalize_unit(
    *,
    row: NormalizedMessage,
    structure_type: str,
    unit_index: int,
    raw_unit: SemanticUnitDraft,
    category_map: dict[str, str],
    theme_map: dict[str, tuple[str, str]],
) -> ClassifiedMessage | None:
    canonical_summary = raw_unit.canonical_summary.strip()
    if not canonical_summary:
        return None

    category_key = _normalize_category_key(raw_unit.category_key, category_map)

    theme_category, main_theme = _normalize_theme(raw_unit.main_theme, theme_map)
    if theme_category:
        category_key = theme_category

    sub_themes: list[str] = []
    pending_theme_categories: list[str] = []
    for theme in raw_unit.sub_themes:
        sub_category, normalized_theme = _normalize_theme(theme, theme_map)
        if not normalized_theme:
            continue
        pending_theme_categories.append(sub_category)
        if normalized_theme == main_theme:
            continue
        if category_key != "unclassified" and sub_category != category_key:
            continue
        sub_themes.append(normalized_theme)

    if main_theme is None and sub_themes:
        first_sub_theme = sub_themes.pop(0)
        main_theme = first_sub_theme
        if category_key == "unclassified" and pending_theme_categories:
            category_key = pending_theme_categories[0]

    sub_themes = _dedupe_preserve_order(sub_themes, limit=2)
    ticker_tags = _dedupe_preserve_order(raw_unit.ticker_tags, limit=5)
    supporting_facts = _dedupe_preserve_order(raw_unit.supporting_facts, limit=5)

    return ClassifiedMessage(
        telegram_message_id=row.telegram_message_id,
        source_date=row.source_date,
        channel_key=row.channel_key,
        source_channel_key=row.source_channel_key,
        processing_mode=row.processing_mode,
        structure_type=structure_type,
        unit_index=unit_index,
        message_type=raw_unit.message_type,
        category_key=category_key,
        main_theme=main_theme,
        sub_themes=sub_themes,
        ticker_tags=ticker_tags,
        canonical_summary=canonical_summary,
        supporting_facts=supporting_facts,
    )


@lru_cache(maxsize=4)
def _get_llm_runtime(provider: str):
    llm_config = get_semantic_extraction_llm_config(provider)
    return llm_config, llm_config.create_llm()


async def _extract_message_semantics(
    *,
    row: NormalizedMessage,
    taxonomy: TaxonomyRegistry,
    provider: str,
) -> SemanticExtractionDraft:
    llm_config, llm = _get_llm_runtime(provider)
    taxonomy_outline = render_taxonomy_outline(taxonomy)
    user_prompt = build_semantic_extraction_user_prompt(
        row,
        taxonomy_outline=taxonomy_outline,
    )
    messages = llm_config.build_messages(
        SEMANTIC_EXTRACTION_SYSTEM_PROMPT,
        user_prompt,
    )
    config = {
        "run_name": f"StockReport Semantic Extraction - {row.telegram_message_id}",
        "tags": [
            "stock_report",
            "semantic_extraction",
            f"provider:{provider}",
            f"channel:{row.channel_key}",
        ],
        "metadata": {
            "telegram_message_id": row.telegram_message_id,
            "provider": provider,
            "channel_key": row.channel_key,
            "source_date": str(row.source_date),
        },
    }
    return await invoke_llm_with_retry(
        llm,
        SemanticExtractionDraft,
        messages,
        config,
        max_retries=SEMANTIC_EXTRACTION_MAX_RETRIES,
        timeout_seconds=SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    )


async def _classify_single_message(
    *,
    row: NormalizedMessage,
    taxonomy: TaxonomyRegistry,
    provider: str,
    category_map: dict[str, str],
    theme_map: dict[str, tuple[str, str]],
    semaphore: asyncio.Semaphore,
) -> list[ClassifiedMessage]:
    if row.processing_mode == "skip" or not row.clean_text.strip():
        return []

    try:
        async with semaphore:
            extraction = await _extract_message_semantics(
                row=row,
                taxonomy=taxonomy,
                provider=provider,
            )
    except Exception as exc:
        logger.warning(
            "Semantic extraction failed for telegram_message_id=%s: %s",
            row.telegram_message_id,
            exc,
        )
        fallback = _build_fallback_message(row)
        return [fallback] if fallback else []

    classified_units: list[ClassifiedMessage] = []
    for unit_index, raw_unit in enumerate(extraction.units):
        normalized = _normalize_unit(
            row=row,
            structure_type=extraction.structure_type,
            unit_index=unit_index,
            raw_unit=raw_unit,
            category_map=category_map,
            theme_map=theme_map,
        )
        if normalized is None:
            continue
        classified_units.append(normalized)
    return classified_units


async def _classify_messages_async(
    normalized_messages: list[NormalizedMessage],
    *,
    taxonomy: TaxonomyRegistry,
    provider: str,
) -> list[ClassifiedMessage]:
    category_map, theme_map = build_match_dictionary(taxonomy)
    semaphore = asyncio.Semaphore(SEMANTIC_EXTRACTION_MAX_CONCURRENCY)
    tasks = [
        _classify_single_message(
            row=row,
            taxonomy=taxonomy,
            provider=provider,
            category_map=category_map,
            theme_map=theme_map,
            semaphore=semaphore,
        )
        for row in normalized_messages
    ]
    results = await asyncio.gather(*tasks)
    return [item for batch in results for item in batch]


def classify_messages(
    normalized_messages: list[NormalizedMessage],
    *,
    taxonomy: TaxonomyRegistry,
    provider: str,
) -> list[ClassifiedMessage]:
    if not normalized_messages:
        return []
    return asyncio.run(
        _classify_messages_async(
            normalized_messages,
            taxonomy=taxonomy,
            provider=provider,
        )
    )
