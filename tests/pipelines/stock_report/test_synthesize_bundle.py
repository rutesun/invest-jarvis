from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.retrieval import (
    CategoryBucket,
    SameDayChunk,
    TickerBucket,
)
from src.pipelines.stock_report.synthesize import (
    EvidenceItem,
    build_category_evidence,
    build_ticker_evidence,
)


def _chunk(
    chunk_id: int,
    *,
    category_key: str = "반도체",
    main_theme: str | None = "HBM",
    ticker_tags: list[str] | None = None,
    supporting_facts: list[str] | None = None,
    evidence_items: list[dict] | None = None,
    canonical_summary: str | None = None,
    channel_name: str | None = "키움 미국주식",
    channel_message_id: str | None = None,
    message_type: str = "signal",
) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 5, 26),
        channel_key="kwusa",
        channel_name=channel_name,
        channel_message_id=channel_message_id or str(50000 + chunk_id),
        message_type=message_type,
        event_type="해석/전망",
        category_key=category_key,
        main_theme=main_theme,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=ticker_tags or [],
        theme_tags=[],
        canonical_summary=canonical_summary or f"summary-{chunk_id}",
        supporting_facts=supporting_facts or [],
        evidence_items=evidence_items if evidence_items is not None else [],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=1.0,
    )


class TestBuildCategoryEvidence:
    def test_returns_one_item_per_chunk(self) -> None:
        chunks = [_chunk(i) for i in range(1, 4)]
        bucket = CategoryBucket(category_key="반도체", chunks=chunks)

        result = build_category_evidence(bucket)

        assert len(result) == 3
        assert all(isinstance(item, EvidenceItem) for item in result)

    def test_chunk_id_matches(self) -> None:
        chunks = [_chunk(10), _chunk(20)]
        bucket = CategoryBucket(category_key="반도체", chunks=chunks)

        result = build_category_evidence(bucket)

        assert [item.chunk_id for item in result] == [10, 20]

    def test_summary_is_preserved(self) -> None:
        chunk = _chunk(1, canonical_summary="NVDA HBM 수요 급증")
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)

        assert result[0].summary == "NVDA HBM 수요 급증"

    def test_supporting_facts_not_truncated(self) -> None:
        facts = [f"fact-{i}" for i in range(10)]
        chunk = _chunk(1, supporting_facts=facts)
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)

        assert result[0].supporting_facts == facts

    def test_supporting_facts_is_a_copy(self) -> None:
        facts = ["fact-a", "fact-b"]
        chunk = _chunk(1, supporting_facts=facts)
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)
        result[0].supporting_facts.append("mutated")

        assert chunk.supporting_facts == facts

    def test_source_format_channel_name_and_message_id(self) -> None:
        chunk = _chunk(1, channel_name="키움 미국주식", channel_message_id="99999")
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)

        assert result[0].source == "키움 미국주식#99999"

    def test_source_falls_back_to_channel_key_when_name_is_none(self) -> None:
        chunk = _chunk(1, channel_name=None)
        # channel_key is always "kwusa" in helper
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)

        assert result[0].source.startswith("kwusa#")

    def test_tickers_preserved(self) -> None:
        chunk = _chunk(1, ticker_tags=["NVDA", "AMD"])
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)

        assert result[0].tickers == ["NVDA", "AMD"]

    def test_tickers_is_a_copy(self) -> None:
        tickers = ["NVDA"]
        chunk = _chunk(1, ticker_tags=tickers)
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)
        result[0].tickers.append("mutated")

        assert chunk.ticker_tags == tickers

    def test_message_type_preserved(self) -> None:
        chunk = _chunk(1, message_type="data")
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)

        assert result[0].message_type == "data"

    def test_evidence_items_not_truncated(self) -> None:
        items = [{"kind": "metric", "text": f"metric-{i}"} for i in range(6)]
        chunk = _chunk(1, evidence_items=items)
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)

        assert result[0].evidence_items == items

    def test_evidence_items_is_a_copy(self) -> None:
        items = [{"kind": "fact", "text": "HBM 수요 증가"}]
        chunk = _chunk(1, evidence_items=items)
        bucket = CategoryBucket(category_key="반도체", chunks=[chunk])

        result = build_category_evidence(bucket)
        result[0].evidence_items.append({"kind": "thesis", "text": "mutated"})

        assert chunk.evidence_items == items

    def test_empty_bucket_returns_empty_list(self) -> None:
        bucket = CategoryBucket(category_key="반도체", chunks=[])

        result = build_category_evidence(bucket)

        assert result == []


class TestBuildTickerEvidence:
    def test_returns_one_item_per_chunk(self) -> None:
        chunks = [_chunk(i, ticker_tags=["NVDA"]) for i in range(1, 5)]
        bucket = TickerBucket(ticker="NVDA", chunks=chunks)

        result = build_ticker_evidence(bucket)

        assert len(result) == 4
        assert all(isinstance(item, EvidenceItem) for item in result)

    def test_chunk_id_matches(self) -> None:
        chunks = [_chunk(5), _chunk(6)]
        bucket = TickerBucket(ticker="NVDA", chunks=chunks)

        result = build_ticker_evidence(bucket)

        assert [item.chunk_id for item in result] == [5, 6]

    def test_supporting_facts_not_truncated(self) -> None:
        facts = [f"fact-{i}" for i in range(8)]
        chunk = _chunk(1, supporting_facts=facts)
        bucket = TickerBucket(ticker="NVDA", chunks=[chunk])

        result = build_ticker_evidence(bucket)

        assert result[0].supporting_facts == facts

    def test_source_format(self) -> None:
        chunk = _chunk(1, channel_name="뉴지스탁", channel_message_id="12345")
        bucket = TickerBucket(ticker="NVDA", chunks=[chunk])

        result = build_ticker_evidence(bucket)

        assert result[0].source == "뉴지스탁#12345"

    def test_evidence_items_preserved(self) -> None:
        items = [
            {"kind": "thesis", "text": "AI 수요 강세"},
            {"kind": "metric", "text": "매출 +40%"},
        ]
        chunk = _chunk(1, evidence_items=items)
        bucket = TickerBucket(ticker="NVDA", chunks=[chunk])

        result = build_ticker_evidence(bucket)

        assert result[0].evidence_items == items

    def test_evidence_items_is_a_copy(self) -> None:
        items = [{"kind": "risk", "text": "공급 부족"}]
        chunk = _chunk(1, evidence_items=items)
        bucket = TickerBucket(ticker="NVDA", chunks=[chunk])

        result = build_ticker_evidence(bucket)
        result[0].evidence_items.append({"kind": "fact", "text": "mutated"})

        assert chunk.evidence_items == items

    def test_empty_bucket_returns_empty_list(self) -> None:
        bucket = TickerBucket(ticker="NVDA", chunks=[])

        result = build_ticker_evidence(bucket)

        assert result == []

    def test_all_chunk_tickers_preserved(self) -> None:
        chunk = _chunk(1, ticker_tags=["NVDA", "AMD", "TSM"])
        bucket = TickerBucket(ticker="NVDA", chunks=[chunk])

        result = build_ticker_evidence(bucket)

        assert result[0].tickers == ["NVDA", "AMD", "TSM"]

    def test_chunks_from_multiple_channels(self) -> None:
        chunk_a = _chunk(1, channel_name="채널A", channel_message_id="1001")
        chunk_b = _chunk(2, channel_name="채널B", channel_message_id="2002")
        bucket = TickerBucket(ticker="삼성전자", chunks=[chunk_a, chunk_b])

        result = build_ticker_evidence(bucket)

        assert result[0].source == "채널A#1001"
        assert result[1].source == "채널B#2002"
