"""PDF 문서 단위 LLM 분류 — category_key/main_theme 채움 (문제 #3, T16 선행).

``extract_metadata``(로컬 규칙)는 파일명·헤딩에 분류 정보가 없어 category/theme을
만들지 못하고 항상 None을 남긴다. 이 모듈은 문서 제목 + 본문 발췌를 taxonomy 기반으로
LLM 분류해 두 값을 채운다. 텔레그램 ``classify_messages``와 **같은 taxonomy**를 써서 두
소스(knowledge_chunks/document_chunks)가 같은 category 좌표계에 있게 한다 — 통합 필터
검색과 Telegram-PDF cross-link(T16)의 전제다.

견고성: LLM 호출은 DB 트랜잭션 밖(``pdf_ingest`` 패스1의 upsert 이전)에서 일어난다.
LLM이 taxonomy 밖 값을 주거나 호출이 실패하면 alias 규칙 매칭(``_fallback_overlay``)으로
보강하고, 그것도 실패하면 (None, None) — 즉 unclassified로 떨어진다(배치 중단 없음).
"""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import BaseModel, field_validator

from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.stock_report.config import (
    SEMANTIC_EXTRACTION_MAX_RETRIES,
    SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    get_semantic_extraction_llm_config,
)
from src.pipelines.stock_report.pdf_parser import ParsedDocument
from src.pipelines.stock_report.taxonomy import (
    TaxonomyRegistry,
    build_match_dictionary,
    render_taxonomy_outline,
)


logger = logging.getLogger(__name__)

# 분류 입력으로 쓸 본문 발췌 최대 길이. 문서 주제는 앞부분(제목/요약/개요)에 드러나므로
# 앞쪽만 써서 토큰을 아낀다.
CLASSIFY_BODY_CHARS = 3000

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


PDF_CLASSIFY_SYSTEM_PROMPT = """당신은 증권사 리서치 PDF를 분류하는 애널리스트다.
주어진 taxonomy의 category와 theme 중에서 이 문서에 가장 맞는 것을 고른다.

규칙:
- category_key는 반드시 제공된 category 목록의 key 중 하나를 그대로 쓴다. 적합한 것이 없으면 "unclassified".
- main_theme은 선택한 category에 속한 theme key 중 하나를 그대로 쓴다. 적합한 것이 없으면 null.
- 추측하지 말고 문서 내용에 근거해 고른다. 단일 산업·종목 리포트는 해당 산업 category로,
  매크로/전략/시황/지수 리포트는 "매크로/정책"으로 분류한다.
- category_key와 main_theme 외에 다른 설명은 출력하지 않는다."""


class PdfClassificationLLMOutput(BaseModel):
    """PDF 분류 LLM 출력 (strict schema 안전: str|None만, dict/list 중첩 없음)."""

    category_key: str | None = None
    main_theme: str | None = None

    @field_validator("category_key", "main_theme", mode="before")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


def build_pdf_classify_user_prompt(
    *,
    title: str | None,
    body_excerpt: str,
    taxonomy_outline: str,
) -> str:
    title_line = title or "(제목 없음)"
    return (
        f"# Taxonomy (category: themes)\n{taxonomy_outline}\n\n"
        f"# 문서 제목\n{title_line}\n\n"
        f"# 문서 본문 발췌\n{body_excerpt}\n\n"
        "이 문서의 category_key와 main_theme을 고르라."
    )


def _body_excerpt(markdown: str, limit: int = CLASSIFY_BODY_CHARS) -> str:
    """이미지 마크업을 제거하고 앞부분만 발췌한다(표/숫자는 분류 신호라 유지)."""
    cleaned = _IMAGE_RE.sub("", markdown).strip()
    return cleaned[:limit]


def _normalize_category(value: str | None, category_map: dict[str, str]) -> str | None:
    """LLM이 준 category 문자열을 taxonomy key로 정규화한다(없으면 None)."""
    if not value:
        return None
    return category_map.get(value.strip().lower())


def _normalize_theme(
    value: str | None,
    theme_map: dict[str, tuple[str, str]],
    category_key: str | None,
) -> str | None:
    """LLM이 준 theme을 taxonomy theme key로 정규화한다.

    theme이 선택된 category에 속하지 않으면 버린다(category-theme 일관성 유지).
    """
    if not value:
        return None
    match = theme_map.get(value.strip().lower())
    if not match:
        return None
    theme_category, theme_key = match
    if category_key and theme_category != category_key:
        return None
    return theme_key


def _fallback_overlay(
    title: str | None,
    body: str,
    taxonomy: TaxonomyRegistry,
) -> tuple[str | None, str | None]:
    """LLM 실패/미정 시 alias 등장 빈도로 category/theme을 추정한다(규칙 fallback)."""
    text = f"{title or ''} {body}".lower()

    best_category: str | None = None
    best_score = 0
    for category in taxonomy.categories:
        score = sum(text.count(alias.lower()) for alias in [category.key, *category.aliases])
        if score > best_score:
            best_category, best_score = category.key, score
    if best_category is None:
        return None, None

    best_theme: str | None = None
    best_theme_score = 0
    category_node = next((c for c in taxonomy.categories if c.key == best_category), None)
    if category_node:
        for theme in category_node.themes:
            score = sum(text.count(alias.lower()) for alias in [theme.key, *theme.aliases])
            if score > best_theme_score:
                best_theme, best_theme_score = theme.key, score

    return best_category, (best_theme if best_theme_score > 0 else None)


async def _classify_async(
    title: str | None,
    body_excerpt: str,
    taxonomy: TaxonomyRegistry,
) -> PdfClassificationLLMOutput:
    llm_config = get_semantic_extraction_llm_config()
    provider = llm_config.provider
    llm = llm_config.create_llm()
    outline = render_taxonomy_outline(taxonomy)
    user_prompt = build_pdf_classify_user_prompt(
        title=title,
        body_excerpt=body_excerpt,
        taxonomy_outline=outline,
    )
    messages = llm_config.build_messages(PDF_CLASSIFY_SYSTEM_PROMPT, user_prompt)
    config = {
        "run_name": "StockReport PDF Classify",
        "tags": ["stock_report", "pdf_classify", f"provider:{provider}"],
        "metadata": {
            "stage": "pdf_classify",
            "provider": provider,
            "model": llm_config.model,
            "title": title or "",
        },
    }
    result = await invoke_llm_with_retry(
        llm,
        PdfClassificationLLMOutput,
        messages,
        config,
        max_retries=SEMANTIC_EXTRACTION_MAX_RETRIES,
        timeout_seconds=SEMANTIC_EXTRACTION_TIMEOUT_SECONDS,
    )
    return result  # type: ignore[return-value]


def classify_document(
    parsed: ParsedDocument,
    *,
    title: str | None,
    taxonomy: TaxonomyRegistry,
) -> tuple[str | None, str | None]:
    """문서 제목 + 본문 발췌를 taxonomy 기반 LLM으로 분류해 (category_key, main_theme) 반환.

    LLM 결과는 taxonomy로 정규화하고, taxonomy 밖이거나 호출 실패면 규칙 fallback을
    쓴다. 본문이 비면 (None, None). 어떤 경우에도 예외를 던지지 않는다(배치 안전).
    """
    body = _body_excerpt(parsed.markdown)
    if not body:
        return None, None

    category_map, theme_map = build_match_dictionary(taxonomy)

    category_key: str | None = None
    main_theme: str | None = None
    try:
        output = asyncio.run(_classify_async(title, body, taxonomy))
        category_key = _normalize_category(output.category_key, category_map)
        main_theme = _normalize_theme(output.main_theme, theme_map, category_key)
    except Exception as exc:  # noqa: BLE001 - 분류 실패가 배치를 막으면 안 된다
        logger.warning("pdf classify LLM 실패, 규칙 fallback 사용: %s", exc)

    if category_key is None:
        category_key, main_theme = _fallback_overlay(title, body, taxonomy)

    return category_key, main_theme
