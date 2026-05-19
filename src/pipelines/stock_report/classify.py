from __future__ import annotations

import asyncio
import logging
import time
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
    CategoryNode,
    TaxonomyRegistry,
    build_match_dictionary,
    render_taxonomy_outline,
)


logger = logging.getLogger(__name__)
MULTISPACE_PATTERN = __import__("re").compile(r"\s+")
NUMERIC_PATTERN = __import__("re").compile(r"[0-9]|%|[+-][0-9]")
NUMERIC_TOKEN_PATTERN = __import__("re").compile(
    r"[+-]?\d[\d,]*(?:\.\d+)?(?:%|bp|bps|x|배|억|조|만|천|원|달러|톤|대|주|명|개|MW|GW)?",
    __import__("re").IGNORECASE,
)
STOCK_CODE_PATTERN = __import__("re").compile(r"\([0-9]{4,6}(?:\.[A-Z]{2})?\)")
PHONE_PATTERN = __import__("re").compile(
    r"(?:☎|tel|전화|문의|[0-9]{2,3}-[0-9]{3,4}-[0-9]{4})",
    __import__("re").IGNORECASE,
)
URL_PATTERN = __import__("re").compile(r"https?://|www\\.", __import__("re").IGNORECASE)
ASCII_WORD_PATTERN = __import__("re").compile(r"^[a-z0-9 _./+-]+$")
SIGNAL_HINT_KEYWORDS = (
    "상장",
    "협약",
    "체결",
    "인증",
    "승인",
    "수주",
    "인수",
    "합병",
    "출시",
    "공시",
    "가이던스",
    "투자",
    "파트너십",
    "개발 성공",
    "정책 발표",
)
DATA_HINT_KEYWORDS = (
    "yoy",
    "qoq",
    "전년비",
    "증가",
    "감소",
    "비중",
    "판매",
    "등록",
    "점유율",
    "매출",
    "영업이익",
    "eps",
    "통계",
    "지수",
)
OPINION_HINT_KEYWORDS = ("전망", "추정", "코멘트", "의견", "우려", "판단", "가능성")
ADMIN_HINT_KEYWORDS = ("공지", "안내", "구독", "입장", "문의", "채널")
REPORT_DISCLOSURE_KEYWORDS = (
    "조사분석자료",
    "공표 승인",
    "배포되는 자료",
    "재배포",
    "원문 확인",
)
REPORT_BYLINE_KEYWORDS = (
    "기업분석부",
    "리서치센터",
    "애널리스트",
)
LEAD_TITLE_PREFIXES = (
    "[",
    "**[",
    "★",
    "☀",
    "S&P",
)
LEAD_TITLE_KEYWORDS = (
    "map",
    "daily market digest",
    "리서치 요약",
    "퀀트 시그널",
    "데일리 뉴스",
    "증시 개장 전",
)
SUPPORTING_FACT_LIMIT = 20
EVENT_TYPE_ALIAS_MAP = {
    "자본조달": "자본조달",
    "전환사채": "자본조달",
    "cb": "자본조달",
    "convertible bond": "자본조달",
    "capped call": "자본조달",
    "수주/계약": "수주/계약",
    "계약": "수주/계약",
    "수주": "수주/계약",
    "파트너십": "수주/계약",
    "partnership": "수주/계약",
    "실적": "실적",
    "earnings": "실적",
    "가이던스": "실적",
    "정책": "정책",
    "규제": "정책",
    "policy": "정책",
    "인증/승인": "인증/승인",
    "인증": "인증/승인",
    "승인": "인증/승인",
    "approval": "인증/승인",
    "certification": "인증/승인",
    "m&a": "M&A",
    "인수합병": "M&A",
    "인수": "M&A",
    "합병": "M&A",
    "출시/제품": "출시/제품",
    "출시": "출시/제품",
    "제품": "출시/제품",
    "price/margin": "가격/마진",
    "가격/마진": "가격/마진",
    "가격": "가격/마진",
    "마진": "가격/마진",
    "통계/지표": "통계/지표",
    "통계": "통계/지표",
    "지표": "통계/지표",
    "해석/전망": "해석/전망",
    "전망": "해석/전망",
    "코멘트": "해석/전망",
    "공지": "공지",
}


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


def _normalize_event_type(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return EVENT_TYPE_ALIAS_MAP.get(stripped.lower(), stripped)


def _extract_numeric_tokens(text: str) -> list[str]:
    if not text:
        return []

    tokens: list[str] = []
    seen: set[str] = set()
    for match in NUMERIC_TOKEN_PATTERN.findall(text):
        token = match.strip()
        if not token:
            continue
        digits = "".join(ch for ch in token if ch.isdigit())
        if len(digits) < 2 and "%" not in token:
            continue
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tokens.append(token)
    return tokens


def _ensure_numeric_supporting_fact(
    *,
    source_text: str,
    supporting_facts: list[str],
    structure_type: str,
) -> list[str]:
    if structure_type != "single_topic_deep":
        return supporting_facts

    source_tokens = _extract_numeric_tokens(source_text)
    if not source_tokens:
        return supporting_facts

    for fact in supporting_facts:
        if _extract_numeric_tokens(fact):
            return supporting_facts

    numeric_fact = f"핵심 수치: {', '.join(source_tokens[:3])}"
    trimmed = (
        supporting_facts[: SUPPORTING_FACT_LIMIT - 1]
        if len(supporting_facts) >= SUPPORTING_FACT_LIMIT
        else supporting_facts
    )
    return _dedupe_preserve_order([*trimmed, numeric_fact], limit=SUPPORTING_FACT_LIMIT)


def _extract_lead_comment(text: str) -> str | None:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines:
                break
            continue
        if lines and (line.startswith("[") or line.startswith("* ") or line.startswith("- ")):
            break
        lines.append(line)
        if len(lines) >= 2:
            break

    if not lines:
        return None
    lead_comment = " ".join(lines).strip()
    if _looks_like_report_header_or_byline(lead_comment):
        return None
    return lead_comment or None


def _looks_like_report_header_or_byline(text: str) -> bool:
    if not text:
        return False

    normalized = text.strip()
    lowered = normalized.lower()
    if len(normalized) > 120:
        return True
    if URL_PATTERN.search(normalized):
        return True
    if any(lowered.startswith(prefix.lower()) for prefix in LEAD_TITLE_PREFIXES):
        return True
    if any(keyword in lowered for keyword in LEAD_TITLE_KEYWORDS):
        return True
    if ASCII_WORD_PATTERN.match(lowered):
        return True
    if PHONE_PATTERN.search(text):
        return True
    if STOCK_CODE_PATTERN.search(text):
        return True
    if any(keyword in text for keyword in REPORT_BYLINE_KEYWORDS):
        return True
    return text.startswith(("『", "「")) and text.endswith(("』", "」"))


def _ensure_lead_numeric_supporting_fact(
    *,
    source_text: str,
    supporting_facts: list[str],
) -> list[str]:
    lead_comment = _extract_lead_comment(source_text)
    if not lead_comment or not _extract_numeric_tokens(lead_comment):
        return supporting_facts

    joined_facts = " ".join(supporting_facts)
    if lead_comment in joined_facts:
        return supporting_facts

    lead_fact = f"작성자 코멘트: {lead_comment}"
    return _dedupe_preserve_order(
        [lead_fact, *supporting_facts],
        limit=SUPPORTING_FACT_LIMIT,
    )


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
        event_type=None,
        category_key="unclassified",
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        canonical_summary=canonical_summary,
        supporting_facts=[],
    )


def _build_overlay_text(*parts: str) -> str:
    joined = " ".join(part.strip() for part in parts if part and part.strip())
    return MULTISPACE_PATTERN.sub(" ", joined).lower()


def _is_valid_overlay_alias(alias: str) -> bool:
    stripped = alias.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if ASCII_WORD_PATTERN.fullmatch(lowered):
        return len(lowered.replace(" ", "")) >= 3
    return len(stripped) >= 2


def _score_overlay_alias(
    *,
    alias: str,
    summary_text: str,
    facts_text: str,
    clean_text: str,
    raw_text: str,
) -> int:
    if not _is_valid_overlay_alias(alias):
        return 0
    needle = alias.lower()
    score = 0
    if needle in summary_text:
        score += 3
    if needle in facts_text:
        score += 2
    if needle in raw_text:
        score += 2
    if needle in clean_text:
        score += 1
    return score


def _match_category_overlay(
    *,
    taxonomy: TaxonomyRegistry,
    summary_text: str,
    facts_text: str,
    clean_text: str,
    raw_text: str,
) -> str | None:
    best_category: str | None = None
    best_score = 0
    for category in taxonomy.categories:
        aliases = [category.key, *category.aliases]
        score = sum(
            _score_overlay_alias(
                alias=alias,
                summary_text=summary_text,
                facts_text=facts_text,
                clean_text=clean_text,
                raw_text=raw_text,
            )
            for alias in aliases
        )
        if score > best_score:
            best_category = category.key
            best_score = score
    if best_score < 3:
        return None
    return best_category


def _match_theme_overlay(
    *,
    taxonomy: TaxonomyRegistry,
    summary_text: str,
    facts_text: str,
    clean_text: str,
    raw_text: str,
    category_key: str | None,
) -> tuple[str | None, str | None]:
    categories: list[CategoryNode]
    if category_key:
        categories = [node for node in taxonomy.categories if node.key == category_key]
    else:
        categories = list(taxonomy.categories)

    best_theme: str | None = None
    best_category: str | None = category_key
    best_score = 0
    for category in categories:
        for theme in category.themes:
            aliases = [theme.key, *theme.aliases]
            score = sum(
                _score_overlay_alias(
                    alias=alias,
                    summary_text=summary_text,
                    facts_text=facts_text,
                    clean_text=clean_text,
                    raw_text=raw_text,
                )
                for alias in aliases
            )
            if score > best_score:
                best_theme = theme.key
                best_category = category.key
                best_score = score
    if best_score < 3:
        return category_key, None
    return best_category, best_theme


def _normalize_message_type(
    raw_message_type: str,
    *,
    canonical_summary: str,
    supporting_facts: list[str],
) -> str:
    merged_text = f"{canonical_summary} {' '.join(supporting_facts)}".strip()
    lowered = merged_text.lower()

    has_investment_content = any(
        keyword in merged_text or keyword in lowered
        for keyword in SIGNAL_HINT_KEYWORDS + DATA_HINT_KEYWORDS + OPINION_HINT_KEYWORDS
    )
    if any(keyword in merged_text for keyword in REPORT_DISCLOSURE_KEYWORDS):
        has_investment_content = True

    if (
        any(keyword in merged_text for keyword in ADMIN_HINT_KEYWORDS)
        and not has_investment_content
    ):
        return "admin"
    if raw_message_type == "admin":
        if has_investment_content:
            return "opinion"
        return "admin"

    if raw_message_type == "opinion":
        return "opinion"
    if any(keyword in merged_text for keyword in OPINION_HINT_KEYWORDS) and not any(
        keyword in merged_text for keyword in SIGNAL_HINT_KEYWORDS
    ):
        return "opinion"

    signal_score = sum(1 for keyword in SIGNAL_HINT_KEYWORDS if keyword in merged_text)
    data_score = sum(1 for keyword in DATA_HINT_KEYWORDS if keyword in lowered)
    has_numeric = bool(NUMERIC_PATTERN.search(merged_text))

    if raw_message_type == "data":
        if signal_score >= 2:
            return "signal"
        if signal_score >= 1 and data_score <= 2:
            return "signal"
        return "data"

    if raw_message_type == "signal":
        if signal_score == 0 and data_score >= 3 and has_numeric:
            return "data"
        return "signal"

    return "signal"


def _normalize_unit(
    *,
    row: NormalizedMessage,
    taxonomy: TaxonomyRegistry,
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
    supporting_facts = _dedupe_preserve_order(
        raw_unit.supporting_facts,
        limit=SUPPORTING_FACT_LIMIT,
    )
    supporting_facts = _ensure_numeric_supporting_fact(
        source_text=row.clean_text,
        supporting_facts=supporting_facts,
        structure_type=structure_type,
    )
    supporting_facts = _ensure_lead_numeric_supporting_fact(
        source_text=row.raw_text,
        supporting_facts=supporting_facts,
    )
    event_type = _normalize_event_type(raw_unit.event_type)

    provisional_category: str | None = None
    provisional_theme: str | None = None
    if category_key == "unclassified" or main_theme is None:
        summary_text = _build_overlay_text(canonical_summary)
        facts_text = _build_overlay_text(" ".join(supporting_facts))
        clean_text = _build_overlay_text(row.clean_text)
        raw_text = _build_overlay_text(
            canonical_summary,
            raw_unit.category_key or "",
            raw_unit.main_theme or "",
            " ".join(raw_unit.sub_themes),
        )
        if category_key == "unclassified":
            provisional_category = _match_category_overlay(
                taxonomy=taxonomy,
                summary_text=summary_text,
                facts_text=facts_text,
                clean_text=clean_text,
                raw_text=raw_text,
            )
        overlay_category = category_key if category_key != "unclassified" else provisional_category
        overlay_theme_category, overlay_theme = _match_theme_overlay(
            taxonomy=taxonomy,
            summary_text=summary_text,
            facts_text=facts_text,
            clean_text=clean_text,
            raw_text=raw_text,
            category_key=overlay_category,
        )
        if main_theme is None:
            provisional_theme = overlay_theme
            if category_key == "unclassified" and provisional_category is None:
                provisional_category = overlay_theme_category

    return ClassifiedMessage(
        telegram_message_id=row.telegram_message_id,
        source_date=row.source_date,
        channel_key=row.channel_key,
        source_channel_key=row.source_channel_key,
        processing_mode=row.processing_mode,
        structure_type=structure_type,
        unit_index=unit_index,
        message_type=_normalize_message_type(
            raw_unit.message_type,
            canonical_summary=canonical_summary,
            supporting_facts=supporting_facts,
        ),
        event_type=event_type,
        category_key=category_key,
        main_theme=main_theme,
        provisional_category=provisional_category,
        provisional_theme=provisional_theme,
        is_provisional=bool(provisional_category),
        sub_themes=sub_themes,
        ticker_tags=ticker_tags,
        canonical_summary=canonical_summary,
        supporting_facts=supporting_facts,
    )


@lru_cache(maxsize=4)
def _get_llm_runtime(provider: str):
    llm_config = get_semantic_extraction_llm_config(provider)
    logger.info(
        "Semantic extraction runtime initialized: provider=%s model=%s temperature=%.2f",
        provider,
        llm_config.model,
        llm_config.temperature,
    )
    return llm_config, llm_config.create_llm()


async def _extract_message_semantics(
    *,
    row: NormalizedMessage,
    taxonomy: TaxonomyRegistry,
    provider: str,
    system_prompt: str,
) -> SemanticExtractionDraft:
    llm_config, llm = _get_llm_runtime(provider)
    taxonomy_outline = render_taxonomy_outline(taxonomy)
    user_prompt = build_semantic_extraction_user_prompt(
        row,
        taxonomy_outline=taxonomy_outline,
    )
    messages = llm_config.build_messages(
        system_prompt,
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
    system_prompt: str,
) -> list[ClassifiedMessage]:
    if row.processing_mode == "skip" or not row.clean_text.strip():
        return []

    try:
        async with semaphore:
            extraction = await _extract_message_semantics(
                row=row,
                taxonomy=taxonomy,
                provider=provider,
                system_prompt=system_prompt,
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
            taxonomy=taxonomy,
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
    system_prompt: str,
) -> list[ClassifiedMessage]:
    started_at = time.perf_counter()
    category_map, theme_map = build_match_dictionary(taxonomy)
    logger.info(
        "Semantic extraction batch started: provider=%s messages=%d max_concurrency=%d",
        provider,
        len(normalized_messages),
        SEMANTIC_EXTRACTION_MAX_CONCURRENCY,
    )
    semaphore = asyncio.Semaphore(SEMANTIC_EXTRACTION_MAX_CONCURRENCY)
    tasks = [
        _classify_single_message(
            row=row,
            taxonomy=taxonomy,
            provider=provider,
            category_map=category_map,
            theme_map=theme_map,
            semaphore=semaphore,
            system_prompt=system_prompt,
        )
        for row in normalized_messages
    ]
    results = await asyncio.gather(*tasks)
    flattened = [item for batch in results for item in batch]
    logger.info(
        "Semantic extraction batch completed: provider=%s messages=%d units=%d elapsed=%.2fs",
        provider,
        len(normalized_messages),
        len(flattened),
        time.perf_counter() - started_at,
    )
    return flattened


def classify_messages(
    normalized_messages: list[NormalizedMessage],
    *,
    taxonomy: TaxonomyRegistry,
    provider: str,
    system_prompt: str | None = None,
) -> list[ClassifiedMessage]:
    if not normalized_messages:
        return []
    resolved_system_prompt = system_prompt or SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    return asyncio.run(
        _classify_messages_async(
            normalized_messages,
            taxonomy=taxonomy,
            provider=provider,
            system_prompt=resolved_system_prompt,
        )
    )
