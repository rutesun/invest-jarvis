from __future__ import annotations

from datetime import UTC, date, datetime

from src.pipelines.stock_report.classify import classify_messages
from src.pipelines.stock_report.models import NormalizedMessage
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


def test_classify_assigns_category_theme_and_tickers():
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("HBM 수요 증가로 NVDA 강세")

    result = classify_messages([row], taxonomy=taxonomy)
    assert len(result) == 1
    assert result[0].category_key == "반도체"
    assert result[0].main_theme == "메모리"
    assert result[0].ticker_tags == ["NVDA"]


def test_classify_sets_canonical_summary():
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("AI 데이터센터 전력 수요 급증으로 전력 장비주 강세 지속")

    result = classify_messages([row], taxonomy=taxonomy)
    assert result[0].canonical_summary


def test_classify_message_type_data_and_admin():
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    data_row = _normalized_message("매출 1200 억, 영업이익 320 억, EPS 120, +4.2%")
    admin_row = _normalized_message("채널 공지: 오늘 라이브 안내")

    result = classify_messages([data_row, admin_row], taxonomy=taxonomy)
    assert result[0].message_type == "data"
    assert result[1].message_type == "admin"


def test_classify_does_not_mark_research_summary_as_admin():
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    research_row = _normalized_message(
        "[✨ 리서치 요약] LG 목표주가 상향 리포트 요약 / 투자의견 매수 유지"
    )

    result = classify_messages([research_row], taxonomy=taxonomy)
    assert result[0].message_type == "opinion"


def test_classify_data_overrides_channel_boilerplate():
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    data_with_channel = _normalized_message(
        "[5월 7일, 전세계 반도체 밸류 체인 주가] ☀️채널: TSMC -1%, NVIDIA +2%, AMD -3%, "
        "Intel -2%, Micron -1%"
    )

    result = classify_messages([data_with_channel], taxonomy=taxonomy)
    assert result[0].message_type == "data"


def test_classify_strong_event_keywords_as_signal():
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    event_row = _normalized_message("실적공시: 가이던스 상향 발표, AI 수주 확대")

    result = classify_messages([event_row], taxonomy=taxonomy)
    assert result[0].message_type == "signal"
