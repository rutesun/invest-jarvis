from __future__ import annotations

from datetime import UTC, date, datetime

from src.pipelines.stock_report.classify import classify_messages
from src.pipelines.stock_report.models import (
    NormalizedMessage,
    SemanticExtractionDraft,
    SemanticUnitDraft,
)
from src.pipelines.stock_report.taxonomy import load_taxonomy_registry


def _normalized_message(clean_text: str) -> NormalizedMessage:
    return NormalizedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        channel_key="hana_us_stock",
        source_channel_key="hana_us_stock",
        source_channel_name="hana_us_stock",
        channel_message_id="1",
        raw_text=clean_text,
        clean_text=clean_text,
        urls=[],
        has_media=False,
        content_hash="hash",
        processing_mode="full",
        grouped_message_ids=[],
    )


def test_classify_normalizes_llm_output_into_canonical_fields(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("NVIDIA·IREN, 최대 5GW AI 인프라 구축 전략적 파트너십 발표")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider):
        assert row.clean_text
        assert provider == "openai"
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    category_key="AI infra",
                    main_theme="데이터센터 전력",
                    sub_themes=["AI 칩"],
                    ticker_tags=["NVDA", "IREN"],
                    canonical_summary="NVIDIA·IREN, 최대 5GW AI 인프라 파트너십 발표",
                    supporting_facts=[
                        "양사는 IREN 데이터센터 파이프라인 전반에 NVIDIA 인프라 배치를 추진",
                        "스페인 Ingenostrum 인수로 IREN 전력 포트폴리오가 확대될 예정",
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].structure_type == "single_topic_deep"
    assert result[0].unit_index == 0
    assert result[0].category_key == "AI인프라"
    assert result[0].main_theme == "AI 데이터센터 전력"
    assert result[0].sub_themes == ["AI 반도체"]
    assert result[0].ticker_tags == ["NVDA", "IREN"]
    assert result[0].canonical_summary == "NVIDIA·IREN, 최대 5GW AI 인프라 파트너십 발표"
    assert len(result[0].supporting_facts) == 2


def test_classify_splits_multi_item_digest_into_multiple_report_units(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("신한 자동차 뉴스 digest")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider):
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    category_key="자동차",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["현대차"],
                    canonical_summary="현대차, 보스턴다이내믹스 상장 검토",
                    supporting_facts=[],
                ),
                SemanticUnitDraft(
                    message_type="data",
                    category_key="자동차",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["기아"],
                    canonical_summary="기아 인도 EV 판매 900% 넘게 증가",
                    supporting_facts=[],
                ),
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="anthropic")

    assert len(result) == 2
    assert [item.structure_type for item in result] == ["multi_item_digest", "multi_item_digest"]
    assert [item.unit_index for item in result] == [0, 1]
    assert [item.canonical_summary for item in result] == [
        "현대차, 보스턴다이내믹스 상장 검토",
        "기아 인도 EV 판매 900% 넘게 증가",
    ]


def test_classify_uses_theme_category_when_llm_category_is_missing(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("임상 결과 발표")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    category_key=None,
                    main_theme="임상",
                    sub_themes=["FDA"],
                    ticker_tags=["알테오젠"],
                    canonical_summary="알테오젠, 임상 데이터 발표로 신약개발 기대 부각",
                    supporting_facts=[],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].category_key == "바이오/헬스케어"
    assert result[0].main_theme == "신약개발"
    assert result[0].sub_themes == []


def test_classify_filters_blank_units_from_llm_output(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("운영 공지")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider):
        return SemanticExtractionDraft(
            structure_type="notice",
            units=[
                SemanticUnitDraft(
                    message_type="admin",
                    category_key=None,
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="   ",
                    supporting_facts=[],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert result == []
