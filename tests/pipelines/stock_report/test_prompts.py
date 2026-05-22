from __future__ import annotations

from datetime import UTC, date, datetime

from src.pipelines.stock_report.models import NormalizedMessage
from src.pipelines.stock_report.prompts import (
    SEMANTIC_EXTRACTION_SYSTEM_PROMPT,
    build_semantic_extraction_user_prompt,
)


def _normalized_message() -> NormalizedMessage:
    return NormalizedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        channel_key="ked_epic_ai",
        source_channel_key="ked_epic_ai",
        source_channel_name="ked_epic_ai",
        channel_message_id="1",
        raw_text="반도체 랠리와 유가 급등, 국내 증시 반응을 함께 다룬 시황",
        clean_text="반도체 랠리와 유가 급등, 국내 증시 반응을 함께 다룬 시황",
        urls=[],
        has_media=False,
        content_hash="hash",
        processing_mode="full",
        grouped_message_ids=[],
    )


def test_system_prompt_requires_market_wrap_split_when_narratives_differ():
    assert "market_wrap" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "서로 다른 핵심 내러티브가 2개 이상이면 unit을 분리" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert (
        "`category_key`는 이벤트 종류가 아니라 투자 내러티브/섹터"
        in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    )
    assert "event_type" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "evidence_items" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "supporting_facts" not in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "thesis" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "risk" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "market_context" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "작성자 코멘트" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "하단 고지 때문에 `admin`으로 분류하지 않는다" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "원문보다 더 길게 확장" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "80자 이내" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    assert "최소 1개 이상 반드시 포함" in SEMANTIC_EXTRACTION_SYSTEM_PROMPT


def test_user_prompt_mentions_market_wrap_multi_narrative_split():
    prompt = build_semantic_extraction_user_prompt(
        _normalized_message(),
        taxonomy_outline="- 반도체: 메모리\n- 매크로/정책: 환율/원자재",
    )

    assert "market_wrap" in prompt
    assert "주제가 다르면 unit을 나눈다" in prompt
    assert "내러티브/섹터" in prompt
    assert "event_type" in prompt
