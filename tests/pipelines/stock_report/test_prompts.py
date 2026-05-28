from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.prompts import build_report_synthesis_user_prompt
from src.pipelines.stock_report.retrieval import SameDayBundle, SameDayChunk, TickerBucket


def _chunk(chunk_id: int) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 5, 26),
        channel_key="kwusa",
        channel_name="키움 미국주식",
        channel_message_id="58373",
        message_type="signal",
        event_type="실적",
        category_key="반도체",
        main_theme="HBM",
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=["NVDA"],
        theme_tags=["HBM"],
        canonical_summary="HBM 공급 부족이 이어진다",
        supporting_facts=["HBM 수요 증가"],
        evidence_items=[{"kind": "metric", "text": "HBM 가격 +20%"}],
        qa_warnings=[],
        content_clean="원문",
        priority_score=1.0,
    )


def test_report_synthesis_prompt_documents_card_priority_and_theme_rules() -> None:
    prompt = build_report_synthesis_user_prompt(
        SameDayBundle(
            report_date=date(2026, 5, 26),
            chunks=[_chunk(1)],
            category_buckets=[],
            focus_ticker_buckets=[],
            low_confidence_chunks=[],
        )
    )

    assert "카드는 자르지 말고" in prompt
    assert "priority_score" in prompt
    assert "pulse는 가능하면 서로 다른 category/theme" in prompt
    assert "Core Themes" in prompt
    assert "상위 카테고리 반복 요약이 아니라" in prompt
    assert "thesis" in prompt
    assert "watch_points" in prompt
    assert "related_categories" in prompt
    assert "최소 2개 이상의 category" in prompt
    assert "investment_case" in prompt
    assert "catalysts" in prompt
    assert "risks_or_watch_points" in prompt
    assert "related_themes" in prompt
    assert '"chunk_id": 1' in prompt
    assert '"source": "키움 미국주식#58373"' in prompt


def test_report_synthesis_prompt_includes_richer_focus_ticker_packet() -> None:
    chunk = _chunk(1)
    chunk.evidence_items.extend(
        [
            {"kind": "metric", "text": "AI 서버 매출 +38%"},
            {"kind": "metric", "text": "데이터센터 매출 +57%"},
            {"kind": "thesis", "text": "AI 투자 사이클이 실적 가시성을 높인다"},
            {"kind": "risk", "text": "빅테크 CAPEX 둔화 시 수요가 약해질 수 있다"},
        ]
    )
    chunk.supporting_facts.extend(
        [
            "HBM 공급 부족",
            "고부가 제품 믹스 개선",
            "다년 공급 계약",
            "메모리 가격 상승",
        ]
    )

    prompt = build_report_synthesis_user_prompt(
        SameDayBundle(
            report_date=date(2026, 5, 26),
            chunks=[chunk],
            category_buckets=[],
            focus_ticker_buckets=[TickerBucket(ticker="NVDA", chunks=[chunk])],
            low_confidence_chunks=[],
        )
    )

    assert '"focus_ticker_packet"' in prompt
    assert '"ticker": "NVDA"' in prompt
    assert '"detail_level": "deep"' in prompt
    assert "데이터센터 매출 +57%" in prompt
    assert "AI 투자 사이클이 실적 가시성을 높인다" in prompt
    assert "빅테크 CAPEX 둔화 시 수요가 약해질 수 있다" in prompt
    assert "다년 공급 계약" in prompt
