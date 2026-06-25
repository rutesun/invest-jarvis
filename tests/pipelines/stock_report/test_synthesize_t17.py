"""Task 3 — synthesize search_fn wiring + PDF evidence ref generation tests."""

from __future__ import annotations

import asyncio
from datetime import date

from src.pipelines.stock_report.retrieval import (
    CategoryBucket,
    DocumentSearchHit,
    SameDayChunk,
    TickerBucket,
)
from src.pipelines.stock_report.synthesize import (
    CategorySummaryCard,
    TickerCard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk(chunk_id: int, category_key: str = "반도체") -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 6, 22),
        channel_key="test_channel",
        channel_name="테스트",
        channel_message_id=str(chunk_id),
        message_type="signal",
        event_type="해석/전망",
        category_key=category_key,
        main_theme="AI",
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        theme_tags=[],
        canonical_summary=f"summary-{chunk_id}",
        supporting_facts=[f"fact-{chunk_id}"],
        evidence_items=[{"kind": "metric", "text": f"metric-{chunk_id}"}],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=1.0,
    )


def _major_category_bucket() -> CategoryBucket:
    """chunk 수가 threshold 이상인 major 버킷."""
    return CategoryBucket(category_key="tech", chunks=[_chunk(i) for i in range(1, 6)])


def _major_ticker_bucket() -> TickerBucket:
    return TickerBucket(ticker="NVDA", chunks=[_chunk(i) for i in range(10, 15)])


def _make_pdf_hit(chunk_id: int) -> DocumentSearchHit:
    return DocumentSearchHit(
        chunk_id=chunk_id,
        document_id=chunk_id * 10,
        doc_title=f"PDF Report {chunk_id}",
        source_path=f"/pdfs/report{chunk_id}.pdf",
        broker_key="samsung",
        published_date=date(2026, 6, 1),
        section_path="section/1",
        is_table=False,
        content_clean=f"PDF content {chunk_id}",
        category_key="tech",
        main_theme="AI",
        ticker_tags=["NVDA"],
        similarity=0.85,
    )


def _fake_search_fn(query: str, *, category=None, ticker=None, top_k=3) -> list[DocumentSearchHit]:
    return [_make_pdf_hit(9001), _make_pdf_hit(9002)]


# ---------------------------------------------------------------------------
# CardSummaryCard / TickerCard has document_hits field
# ---------------------------------------------------------------------------


def test_category_summary_card_has_document_hits_field() -> None:
    """CategorySummaryCard에 document_hits 필드가 있고 기본값이 빈 리스트다."""
    card = CategorySummaryCard(
        category_key="tech",
        title="기술",
        narrative="narrative",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
    )
    assert hasattr(card, "document_hits")
    assert card.document_hits == []


def test_ticker_card_has_document_hits_field() -> None:
    """TickerCard에 document_hits 필드가 있고 기본값이 빈 리스트다."""
    card = TickerCard(
        ticker="NVDA",
        investment_case="case",
        catalysts=[],
        key_metrics=[],
        risks=[],
        evidence_chunk_ids=[],
    )
    assert hasattr(card, "document_hits")
    assert card.document_hits == []


# ---------------------------------------------------------------------------
# synthesize_category: search_fn=None → 기존 동작 (회귀 가드)
# ---------------------------------------------------------------------------


def test_synthesize_category_no_search_fn_regression(monkeypatch) -> None:
    """search_fn=None 시 기존 경로(_run_synthesis_call)를 사용하고 PDF ref가 없다."""
    from src.pipelines.stock_report.synthesize import CategoryCardLLMOutput, synthesize_category

    fake_output = CategoryCardLLMOutput(
        category_key="tech",
        title="기술",
        narrative="narrative",
        evidence_bullets=["bullet1"],
        impact="high",
        related_stocks=[],
        evidence_chunk_ids=[1, 2],
        priority_score=1.0,
    )

    async def fake_run_synthesis_call(*args, **kwargs):
        return fake_output

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._run_synthesis_call",
        fake_run_synthesis_call,
    )

    bucket = _major_category_bucket()
    card = asyncio.run(synthesize_category(bucket))

    # 기존 동작: document_hits 비어있음
    assert card.document_hits == []
    # evidence_chunk_ids에 텔레그램 chunk id가 있어야 함 (B3 가드의 반대 — 텔레그램은 OK)
    assert isinstance(card.evidence_chunk_ids, list)


# ---------------------------------------------------------------------------
# synthesize_category: search_fn 주입 → tool-calling 경로
# ---------------------------------------------------------------------------


def test_synthesize_category_with_search_fn_uses_tool_calling(monkeypatch) -> None:
    """search_fn 주입 시 invoke_llm_with_tools가 호출되고 document_hits에 hits가 채워진다."""
    from src.pipelines.stock_report.llm_tools import ToolCallRecord, ToolCallTrace
    from src.pipelines.stock_report.synthesize import CategoryCardLLMOutput, synthesize_category

    invoke_calls: list[dict] = []
    hits = [_make_pdf_hit(9001), _make_pdf_hit(9002)]

    fake_output = CategoryCardLLMOutput(
        category_key="tech",
        title="기술",
        narrative="narrative",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
        priority_score=0.8,
    )

    async def fake_invoke_llm_with_tools(llm, output_model, messages, *, search_fn, config, **kwargs):
        invoke_calls.append({"search_fn": search_fn})
        trace = ToolCallTrace(records=[
            ToolCallRecord(query="tech query", category="tech", ticker=None, top_k=3, hits=hits)
        ])
        return fake_output, trace

    class FakeLLMConfig:
        model = "fake-model"
        def create_llm(self):
            return object()
        def build_messages(self, system, user):
            return []

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize.get_report_synthesis_llm_config",
        lambda provider: FakeLLMConfig(),
    )
    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize.invoke_llm_with_tools",
        fake_invoke_llm_with_tools,
    )

    bucket = _major_category_bucket()
    card = asyncio.run(synthesize_category(bucket, search_fn=_fake_search_fn))

    # invoke_llm_with_tools가 호출됨
    assert len(invoke_calls) == 1
    assert invoke_calls[0]["search_fn"] is _fake_search_fn

    # document_hits가 trace에서 채워짐
    assert len(card.document_hits) == 2
    assert card.document_hits[0].chunk_id == 9001


# ---------------------------------------------------------------------------
# B3: PDF id는 evidence_chunk_ids에 들어가면 안 됨
# ---------------------------------------------------------------------------


def test_synthesize_category_pdf_id_not_in_evidence_chunk_ids(monkeypatch) -> None:
    """PDF document_chunk_id가 ReportSectionItem.evidence_chunk_ids에 섞이지 않는다."""
    from src.pipelines.stock_report.llm_tools import ToolCallRecord, ToolCallTrace
    from src.pipelines.stock_report.synthesize import (
        CategoryCardLLMOutput,
        _card_to_category_item,
        synthesize_category,
    )

    hits = [_make_pdf_hit(99999)]  # PDF id

    fake_output = CategoryCardLLMOutput(
        category_key="tech",
        title="기술",
        narrative="n",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],  # LLM은 PDF id를 evidence_chunk_ids에 포함하지 않음
        priority_score=0.5,
    )

    async def fake_invoke(llm, output_model, messages, *, search_fn, config, **kwargs):
        trace = ToolCallTrace(records=[
            ToolCallRecord(query="q", category=None, ticker=None, top_k=3, hits=hits)
        ])
        return fake_output, trace

    class FakeLLMConfig:
        model = "fake-model"
        def create_llm(self): return object()
        def build_messages(self, s, u): return []

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize.get_report_synthesis_llm_config",
        lambda p: FakeLLMConfig(),
    )
    monkeypatch.setattr("src.pipelines.stock_report.synthesize.invoke_llm_with_tools", fake_invoke)

    bucket = _major_category_bucket()
    card = asyncio.run(synthesize_category(bucket, search_fn=_fake_search_fn))
    item = _card_to_category_item(card)

    # B3: PDF id 99999가 evidence_chunk_ids에 없어야 함
    assert 99999 not in item.evidence_chunk_ids


# ---------------------------------------------------------------------------
# _pdf_evidence_refs: card.document_hits → ReportEvidenceRef list
# ---------------------------------------------------------------------------


def test_pdf_evidence_refs_creates_pdf_refs() -> None:
    """_pdf_evidence_refs가 document_hits에서 source_type='pdf' ReportEvidenceRef를 생성한다."""
    from src.pipelines.stock_report.synthesize import _pdf_evidence_refs

    card = CategorySummaryCard(
        category_key="tech",
        title="기술",
        narrative="",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
        document_hits=[_make_pdf_hit(9001), _make_pdf_hit(9002)],
    )
    item_key = "tech"

    refs = _pdf_evidence_refs("category_summaries", item_key, card.document_hits)

    assert len(refs) == 2
    assert all(r.source_type == "pdf" for r in refs)
    assert all(r.knowledge_chunk_id is None for r in refs)
    assert {r.document_chunk_id for r in refs} == {9001, 9002}
    assert all(r.section_key == "category_summaries" for r in refs)
    assert all(r.item_key == item_key for r in refs)
    # snapshot에 evidence_kind='searched' 포함
    assert all(r.knowledge_chunk_snapshot.get("evidence_kind") == "searched" for r in refs)


# ---------------------------------------------------------------------------
# _assemble_tiered_artifact: PDF refs 추가 경로 (B2)
# ---------------------------------------------------------------------------


def test_assemble_tiered_artifact_adds_pdf_refs_from_document_hits() -> None:
    """_assemble_tiered_artifact이 category_cards.document_hits에서 PDF refs를 생성한다."""
    from src.pipelines.stock_report.retrieval import SameDayBundle
    from src.pipelines.stock_report.synthesize import OverviewResult, _assemble_tiered_artifact

    bucket = _major_category_bucket()
    bundle = SameDayBundle(
        report_date=date(2026, 6, 22),
        chunks=list(bucket.chunks),
        category_buckets=[bucket],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    card = CategorySummaryCard(
        category_key="tech",
        title="기술",
        narrative="n",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
        document_hits=[_make_pdf_hit(9001)],
    )

    overview = OverviewResult(pulse=[], core_themes=[], evidence_chunk_ids=[])

    artifact = _assemble_tiered_artifact(bundle, [card], [], overview)

    pdf_refs = [r for r in artifact.evidence_refs if r.source_type == "pdf"]
    assert len(pdf_refs) == 1
    assert pdf_refs[0].document_chunk_id == 9001
    assert pdf_refs[0].knowledge_chunk_id is None


# ---------------------------------------------------------------------------
# minor 버킷: search_fn 미호출
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# search_log_entries: card 필드 + artifact 수집
# ---------------------------------------------------------------------------


def test_category_summary_card_has_search_log_entries_field() -> None:
    """CategorySummaryCard에 search_log_entries 필드가 있고 기본값이 빈 리스트다."""
    card = CategorySummaryCard(
        category_key="tech",
        title="기술",
        narrative="n",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
    )
    assert hasattr(card, "search_log_entries")
    assert card.search_log_entries == []


def test_ticker_card_has_search_log_entries_field() -> None:
    """TickerCard에 search_log_entries 필드가 있고 기본값이 빈 리스트다."""
    card = TickerCard(
        ticker="NVDA",
        investment_case="case",
        catalysts=[],
        key_metrics=[],
        risks=[],
        evidence_chunk_ids=[],
    )
    assert hasattr(card, "search_log_entries")
    assert card.search_log_entries == []


def test_synthesize_category_populates_search_log_entries(monkeypatch) -> None:
    """search_fn 주입 시 synthesize_category가 card.search_log_entries를 채운다."""
    from src.pipelines.stock_report.synthesize import CategoryCardLLMOutput, synthesize_category

    fake_output = CategoryCardLLMOutput(
        category_key="tech",
        title="기술",
        narrative="n",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
        priority_score=0.5,
    )
    from src.pipelines.stock_report.llm_tools import ToolCallRecord, ToolCallTrace

    recorded_hit = _make_pdf_hit(7001)
    fake_trace = ToolCallTrace(records=[
        ToolCallRecord(query="AI 반도체", category="tech", ticker=None, top_k=3, hits=[recorded_hit]),
    ])

    async def fake_invoke(llm, output_model, messages, *, search_fn=None, config=None, **kwargs):
        return fake_output, fake_trace

    class FakeLLMConfig:
        def create_llm(self): return object()
        def build_messages(self, s, u): return []

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize.get_report_synthesis_llm_config",
        lambda p: FakeLLMConfig(),
    )
    monkeypatch.setattr("src.pipelines.stock_report.synthesize.invoke_llm_with_tools", fake_invoke)

    bucket = _major_category_bucket()
    card = asyncio.run(synthesize_category(bucket, search_fn=_fake_search_fn))

    assert len(card.search_log_entries) == 1
    entry = card.search_log_entries[0]
    assert entry.query == "AI 반도체"
    assert entry.label == bucket.category_key
    assert entry.label_type == "category"
    assert entry.hit_count == 1
    assert entry.hit_chunk_ids == [7001]


def test_assemble_tiered_artifact_collects_pdf_search_entries() -> None:
    """_assemble_tiered_artifact이 category/ticker 카드의 search_log_entries를 pdf_search_entries에 모은다."""
    from src.pipelines.stock_report.llm_tools import PdfSearchLogEntry
    from src.pipelines.stock_report.retrieval import SameDayBundle
    from src.pipelines.stock_report.synthesize import OverviewResult, _assemble_tiered_artifact

    entry = PdfSearchLogEntry(
        label="tech", label_type="category", query="AI 반도체",
        category="tech", ticker=None, top_k=3, hit_count=1, hit_chunk_ids=[9001],
    )
    bucket = _major_category_bucket()
    bundle = SameDayBundle(
        report_date=date(2026, 6, 22),
        chunks=list(bucket.chunks),
        category_buckets=[bucket],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )
    card = CategorySummaryCard(
        category_key="tech",
        title="기술",
        narrative="n",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
        search_log_entries=[entry],
    )
    overview = OverviewResult(pulse=[], core_themes=[], evidence_chunk_ids=[])

    artifact = _assemble_tiered_artifact(bundle, [card], [], overview)

    assert hasattr(artifact, "pdf_search_entries")
    assert len(artifact.pdf_search_entries) == 1
    assert artifact.pdf_search_entries[0].query == "AI 반도체"


def test_synthesize_tiered_does_not_call_search_fn_for_minor_buckets(monkeypatch) -> None:
    """minor 버킷(chunk < threshold)에 대해 search_fn이 호출되지 않는다."""
    from src.pipelines.stock_report.retrieval import SameDayBundle
    from src.pipelines.stock_report.synthesize import synthesize_tiered

    search_fn_calls: list[str] = []

    def counting_search_fn(query: str, **kwargs) -> list[DocumentSearchHit]:
        search_fn_calls.append(query)
        return []

    # minor 버킷: chunk 수 < threshold (3)
    minor_bucket = CategoryBucket(category_key="other", chunks=[_chunk(1)])
    bundle = SameDayBundle(
        report_date=date(2026, 6, 22),
        chunks=list(minor_bucket.chunks),
        category_buckets=[minor_bucket],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    # synthesize_tiered는 async이므로 asyncio.run
    asyncio.run(synthesize_tiered(bundle, search_fn=counting_search_fn))

    assert search_fn_calls == []
