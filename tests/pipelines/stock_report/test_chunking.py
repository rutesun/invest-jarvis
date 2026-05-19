from __future__ import annotations

from datetime import UTC, date, datetime

from src.pipelines.stock_report.chunking import (
    build_chunk_drafts,
    build_embed_payload,
)
from src.pipelines.stock_report.models import ClassifiedMessage, NormalizedMessage


def _normalized(
    message_id: int,
    *,
    mode: str = "full",
    grouped_ids: list[int] | None = None,
    clean_text: str | None = None,
) -> NormalizedMessage:
    return NormalizedMessage(
        telegram_message_id=message_id,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=datetime(2026, 5, 8, 9, message_id % 60, tzinfo=UTC),
        channel_key="hana_us_stock",
        source_channel_key="source_channel",
        source_channel_name="소스 채널",
        channel_message_id=str(message_id),
        raw_text=clean_text or f"raw-{message_id}",
        clean_text=clean_text or f"clean-{message_id}",
        urls=[],
        has_media=False,
        content_hash=f"hash-{message_id}",
        processing_mode=mode,
        grouped_message_ids=grouped_ids or [],
    )


def _classified(message_id: int, message_type: str) -> ClassifiedMessage:
    return ClassifiedMessage(
        telegram_message_id=message_id,
        source_date=date(2026, 5, 8),
        channel_key="hana_us_stock",
        source_channel_key="source_channel",
        processing_mode="full",
        structure_type="single_topic_deep",
        unit_index=0,
        message_type=message_type,
        event_type=None,
        category_key="AI인프라",
        main_theme="데이터센터",
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=["전력"],
        ticker_tags=["NVDA"],
        canonical_summary=f"summary-{message_id}",
        supporting_facts=[],
    )


def test_build_chunk_drafts_includes_only_signal_and_data():
    normalized = [
        _normalized(1),
        _normalized(2),
        _normalized(3),
        _normalized(4),
    ]
    classified = [
        _classified(1, "signal"),
        _classified(2, "data"),
        _classified(3, "opinion"),
        _classified(4, "admin"),
    ]

    drafts = build_chunk_drafts(
        normalized_messages=normalized,
        classified_messages=classified,
    )

    assert len(drafts) == 2
    assert {draft.source_pk for draft in drafts} == {1, 2}
    assert {draft.message_type for draft in drafts} == {"signal", "data"}


def test_build_chunk_drafts_creates_single_synthetic_chunk_for_grouped_only():
    normalized = [
        _normalized(10, mode="grouped_only", grouped_ids=[10, 11], clean_text="반도체 강세"),
        _normalized(11, mode="grouped_only", grouped_ids=[10, 11], clean_text="HBM 수급 타이트"),
    ]
    classified = [
        _classified(10, "signal"),
        _classified(11, "data"),
    ]

    drafts = build_chunk_drafts(
        normalized_messages=normalized,
        classified_messages=classified,
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.source_pk == 10
    assert draft.message_type == "data"
    assert draft.category_key == "unclassified"
    assert draft.content_clean == "반도체 강세\nHBM 수급 타이트"
    assert draft.supporting_facts == ["grouped_message_ids=[10, 11]"]


def test_build_embed_payload_contract():
    payload = build_embed_payload(
        canonical_summary="요약 한 줄",
        clean_text="원문 정제 텍스트",
        channel_name="신한 리서치",
        category_key="반도체",
        main_theme="HBM",
        ticker_tags=["NVDA", "AMD"],
    )

    assert payload == (
        "채널: 신한 리서치\n"
        "카테고리: 반도체\n"
        "메인테마: HBM\n"
        "티커: NVDA, AMD\n"
        "요약 한 줄\n"
        "원문 정제 텍스트"
    )


def test_build_chunk_drafts_uses_provisional_category_in_embed_payload():
    normalized = [_normalized(20, clean_text="PCTC 운임과 BAF 시차 이슈")]
    classified = [_classified(20, "signal")]
    classified[0].category_key = "unclassified"
    classified[0].main_theme = None
    classified[0].provisional_category = "운송/물류"
    classified[0].provisional_theme = "연료비/BAF"
    classified[0].is_provisional = True

    drafts = build_chunk_drafts(
        normalized_messages=normalized,
        classified_messages=classified,
    )

    assert len(drafts) == 1
    assert drafts[0].category_key == "unclassified"
    assert drafts[0].provisional_category == "운송/물류"
    assert "카테고리: 운송/물류" in drafts[0].embed_payload
    assert "메인테마: 연료비/BAF" in drafts[0].embed_payload
