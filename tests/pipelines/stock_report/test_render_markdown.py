from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.render_markdown import MarkdownReportBuilder
from src.pipelines.stock_report.synthesize import (
    MINOR_CATEGORY_ITEM_KEY,
    ReportEvidenceRef,
    ReportSectionItem,
    StockReportArtifact,
)


def test_markdown_report_builder_renders_fixed_sections() -> None:
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[
            ReportSectionItem(
                key="pulse-1",
                title="시장 핵심",
                body="오늘은 반도체와 자동차가 핵심 축이었다.",
                evidence_chunk_ids=[1],
            )
        ],
        category_summaries=[
            ReportSectionItem(
                key="반도체",
                title="반도체",
                body="HBM 공급 타이트닝이 이어진다",
                evidence_chunk_ids=[1],
                evidence_bullets=["NVDA HBM 수요 증가", "메모리 가격 반등"],
                impact="반도체 업황 회복 기대가 강화된다",
                related_stocks=[{"name": "엔비디아", "ticker": "NVDA", "catalyst": "HBM 수요"}],
            )
        ],
        core_themes=[
            ReportSectionItem(
                key="HBM",
                title="HBM",
                body="HBM 수급이 타이트하다",
                evidence_chunk_ids=[1],
            )
        ],
        focus_tickers=[
            ReportSectionItem(
                key="NVDA",
                title="NVDA",
                body="AI 데이터센터 수요가 견조하다",
                evidence_chunk_ids=[1],
            )
        ],
        low_confidence_notes=["분류가 애매한 시황"],
        evidence_refs=[
            ReportEvidenceRef(
                section_key="category_summaries",
                item_key="반도체",
                knowledge_chunk_id=1,
                rank_score=1.0,
                knowledge_chunk_snapshot={
                    "channel_name": "신한 리서치",
                    "channel_message_id": "51014",
                    "channel_key": "shinhanresearch",
                },
            )
        ],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "# Daily Stock Report V2 - 2026-05-26" in markdown
    assert "## Pulse" in markdown
    assert "## Category Summaries" in markdown
    assert "## Core Themes" in markdown
    assert "## Focus Tickers" in markdown
    assert "## Low Confidence" in markdown
    # Pulse: title line + indented body
    assert "- 시장 핵심" in markdown
    assert "  - 오늘은 반도체와 자동차가 핵심 축이었다." in markdown
    # grouped/nested layout: label line + indented content
    assert "- Narrative" in markdown
    assert "  - HBM 공급 타이트닝이 이어진다" in markdown  # narrative now surfaced
    assert "- 근거" in markdown
    assert "  - NVDA HBM 수요 증가" in markdown
    assert "- Impact" in markdown
    assert "  - 반도체 업황 회복 기대가 강화된다" in markdown
    assert "- 관련 종목" in markdown
    assert "  - 엔비디아(NVDA): HBM 수요" in markdown
    # 출처 stays on a single comma-separated line
    assert "- 출처: chunk 1 신한 리서치#51014" in markdown


def test_markdown_report_builder_omits_empty_ticker_parentheses() -> None:
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[
            ReportSectionItem(
                key="금융상품",
                title="레버리지 ETF",
                body="",
                related_stocks=[
                    {
                        "name": "삼전닉스",
                        "ticker": None,
                        "catalyst": "2배 레버리지 상품 출시",
                    }
                ],
            )
        ],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "  - 삼전닉스: 2배 레버리지 상품 출시" in markdown
    assert "삼전닉스(-)" not in markdown


def test_markdown_report_builder_omits_duplicate_name_ticker_parentheses() -> None:
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[
            ReportSectionItem(
                key="반도체",
                title="반도체",
                body="",
                related_stocks=[
                    {
                        "name": "삼성전자",
                        "ticker": "삼성전자",
                        "catalyst": "레버리지 ETF 출시",
                    }
                ],
            )
        ],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "  - 삼성전자: 레버리지 ETF 출시" in markdown
    assert "삼성전자(삼성전자)" not in markdown


def test_markdown_report_builder_omits_empty_catalyst_suffix() -> None:
    """Raw-fallback related stocks carry an empty catalyst (``{name: ticker, ticker, catalyst: ""}``).
    The renderer must show just the label, never a dangling ``: -``."""
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[
            ReportSectionItem(
                key="반도체",
                title="반도체",
                body="",
                related_stocks=[
                    {"name": "TSLA", "ticker": "TSLA", "catalyst": ""},
                    {"name": "엔비디아", "ticker": "NVDA", "catalyst": ""},
                ],
            )
        ],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "  - TSLA" in markdown
    assert "TSLA: -" not in markdown
    assert "  - 엔비디아(NVDA)" in markdown
    assert "엔비디아(NVDA): -" not in markdown


def test_markdown_report_builder_renders_rich_core_theme_card() -> None:
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[],
        core_themes=[
            ReportSectionItem(
                key="ai-infra-chain",
                title="AI 데이터센터 투자 사이클이 HBM·전력·부품 수요로 확산",
                body="",
                thesis="AI CAPEX가 GPU를 넘어 HBM, 전력, 커패시터로 확산 중이다.",
                evidence_bullets=[
                    "ADI 데이터센터 매출이 통신 부문의 75%",
                    "SK하이닉스 iHBM 솔루션 공개",
                ],
                impact="AI 수혜가 엔비디아 중심에서 부품·전력·메모리로 넓어진다.",
                watch_points=["빅테크 CAPEX 지속성", "메모리 가격 상승 지속 여부"],
                related_categories=["AI인프라", "반도체", "원전/전력인프라"],
                related_stocks=[
                    {"name": "SK하이닉스", "ticker": "000660", "catalyst": "HBM 고도화"}
                ],
                evidence_chunk_ids=[1, 2],
            )
        ],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "- 핵심 주장" in markdown
    assert "  - AI CAPEX가 GPU를 넘어 HBM, 전력, 커패시터로 확산 중이다." in markdown
    assert "- Impact" in markdown
    assert "  - AI 수혜가 엔비디아 중심에서 부품·전력·메모리로 넓어진다." in markdown
    assert "- 확인 변수" in markdown
    assert "  - 빅테크 CAPEX 지속성" in markdown
    assert "  - 메모리 가격 상승 지속 여부" in markdown
    assert "- 연결 카테고리" in markdown
    assert "  - AI인프라, 반도체, 원전/전력인프라" in markdown


def test_markdown_report_builder_renders_rich_focus_ticker_card() -> None:
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[],
        core_themes=[],
        focus_tickers=[
            ReportSectionItem(
                key="SK하이닉스",
                title="SK하이닉스: ETF 수급과 HBM 기술 모멘텀",
                body="",
                investment_case="HBM 수요와 ETF 수급이 동시에 붙는 대표 수혜주다.",
                catalysts=["iHBM 냉각 솔루션 공개", "단일종목 레버리지 ETF 출시"],
                key_metrics=["주가 5.72% 급등", "열 저항 30% 감소"],
                evidence_bullets=["주가 5.72% 급등", "HBM 패키지용 냉각 솔루션 출시"],
                risks_or_watch_points=["ETF 출시 후 차익실현", "HBM 공급 경쟁 심화"],
                related_themes=["HBM", "반도체 레버리지 ETF"],
                evidence_chunk_ids=[1, 2],
            )
        ],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "- 투자 포인트" in markdown
    assert "  - HBM 수요와 ETF 수급이 동시에 붙는 대표 수혜주다." in markdown
    assert "- 촉매" in markdown
    assert "  - iHBM 냉각 솔루션 공개" in markdown
    assert "  - 단일종목 레버리지 ETF 출시" in markdown
    assert "- 핵심 수치" in markdown
    assert "  - 주가 5.72% 급등" in markdown
    assert "  - 열 저항 30% 감소" in markdown
    assert "- 리스크/확인" in markdown
    assert "  - ETF 출시 후 차익실현" in markdown
    assert "  - HBM 공급 경쟁 심화" in markdown


def test_markdown_report_builder_renders_related_stocks_as_separate_bullets() -> None:
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[
            ReportSectionItem(
                key="ai-infra",
                title="AI 인프라",
                body="",
                related_stocks=[
                    {"name": "삼화콘덴서", "ticker": None, "catalyst": "전력 인프라 수요 증가"},
                    {"name": "삼성전기", "ticker": None, "catalyst": "실리콘 커패시터 공급 기대"},
                ],
            )
        ],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "- 관련 종목" in markdown
    assert "  - 삼화콘덴서: 전력 인프라 수요 증가" in markdown
    assert "  - 삼성전기: 실리콘 커패시터 공급 기대" in markdown
    assert "삼화콘덴서: 전력 인프라 수요 증가, 삼성전기: 실리콘 커패시터 공급 기대" not in markdown


def test_source_line_dedups_by_channel_and_caps() -> None:
    """Issue 2: 출처 must collapse repeated channels, cap at 6 representatives, and note '외 N건'.
    Full chunk-level attribution still lives in the DB (report_evidence); the rendered line is
    a human-facing summary, so it keeps one representative chunk id per channel."""

    def _ref(chunk_id: int, channel: str, msgid: str) -> ReportEvidenceRef:
        return ReportEvidenceRef(
            section_key="category_summaries",
            item_key="반도체",
            knowledge_chunk_id=chunk_id,
            rank_score=1.0,
            knowledge_chunk_snapshot={
                "channel_name": channel,
                "channel_message_id": msgid,
                "channel_key": channel,
            },
        )

    # 채널1 cited 3x (chunks 1-3); 채널2..채널8 cited once each (chunks 4-10) → 8 unique channels.
    refs = [_ref(1, "채널1", "101"), _ref(2, "채널1", "102"), _ref(3, "채널1", "103")]
    refs += [_ref(i, f"채널{i - 2}", str(100 + i)) for i in range(4, 11)]

    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[
            ReportSectionItem(
                key="반도체",
                title="반도체",
                body="HBM 공급 타이트",
                evidence_chunk_ids=list(range(1, 11)),
            )
        ],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=refs,
    )

    markdown = MarkdownReportBuilder().build(artifact)
    source_line = next(line for line in markdown.splitlines() if line.startswith("- 출처:"))

    # 채널1 cited 3x but collapses to a single representative entry.
    assert source_line.count("채널1") == 1
    # Capped at 6 representative entries (each keeps a parseable "chunk {id}" token).
    assert source_line.count("chunk ") == 6
    # 8 unique channels - 6 shown = 2 remaining.
    assert "외 2건" in source_line
    # Channels beyond the cap are dropped from the human line.
    assert "채널8" not in source_line


def test_minor_briefs_item_renders_flat_bullets() -> None:
    """Issue 1: the consolidated '기타 단신' item renders as flat one-liner bullets (not the
    Narrative/Impact/근거 group layout) so the low-signal tail stays compact."""
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[
            ReportSectionItem(
                key=MINOR_CATEGORY_ITEM_KEY,
                title="기타 단신",
                body="",
                evidence_bullets=["바이오: 임상 결과 발표", "[M&A] 금융: 인수 합의"],
                evidence_chunk_ids=[4, 5],
            )
        ],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)
    section = markdown.split("### 기타 단신", 1)[1]

    assert "### 기타 단신" in markdown
    assert "- 바이오: 임상 결과 발표" in markdown
    assert "- [M&A] 금융: 인수 합의" in markdown
    # flat list — no nested group labels for this item
    assert "- Narrative" not in section
    assert "- 근거" not in section


def test_body_not_duplicated_when_equal_to_thesis_or_investment_case() -> None:
    """Core Themes / Focus Tickers must not render body when it duplicates
    thesis (core theme) or investment_case (focus ticker)."""
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=[],
        category_summaries=[],
        core_themes=[
            ReportSectionItem(
                key="t",
                title="AI 확산",
                body="AI 투자가 밸류체인 전반으로 번진다",
                thesis="AI 투자가 밸류체인 전반으로 번진다",
                evidence_chunk_ids=[1],
            )
        ],
        focus_tickers=[
            ReportSectionItem(
                key="NVDA",
                title="NVDA",
                body="AI 칩 수요 강세가 지속된다",
                investment_case="AI 칩 수요 강세가 지속된다",
                evidence_chunk_ids=[1],
            )
        ],
        low_confidence_notes=[],
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert markdown.count("AI 투자가 밸류체인 전반으로 번진다") == 1
    assert markdown.count("AI 칩 수요 강세가 지속된다") == 1


# ---------------------------------------------------------------------------
# T17: source_type dispatch tests
# ---------------------------------------------------------------------------


def _make_artifact_with_refs(refs: list[ReportEvidenceRef]) -> StockReportArtifact:
    return StockReportArtifact(
        report_date=date(2026, 6, 22),
        pulse=[],
        category_summaries=[
            ReportSectionItem(
                key="반도체",
                title="반도체",
                body="narrative",
                evidence_chunk_ids=[],
                evidence_bullets=["bullet1"],
                impact="high",
            )
        ],
        core_themes=[],
        focus_tickers=[],
        low_confidence_notes=[],
        evidence_refs=refs,
    )


def test_pdf_ref_renders_as_doc_format() -> None:
    """PDF 출처는 'doc {id} {broker} · {title}' 형식으로 렌더된다."""
    artifact = _make_artifact_with_refs(
        [
            ReportEvidenceRef(
                section_key="category_summaries",
                item_key="반도체",
                rank_score=0.9,
                knowledge_chunk_snapshot={
                    "evidence_kind": "searched",
                    "doc_title": "반도체 전망 리포트",
                    "broker_key": "samsung",
                },
                source_type="pdf",
                document_chunk_id=9001,
            )
        ]
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "doc 9001" in markdown
    assert "samsung" in markdown
    # B3 가드: chunk 형식이 아니어야 함
    assert "chunk 9001" not in markdown


def test_telegram_ref_renders_as_chunk_format() -> None:
    """텔레그램 출처는 기존 'chunk {id} {channel}#{msg}' 형식을 유지한다 (회귀 가드)."""
    artifact = _make_artifact_with_refs(
        [
            ReportEvidenceRef(
                section_key="category_summaries",
                item_key="반도체",
                knowledge_chunk_id=1234,
                rank_score=1.0,
                knowledge_chunk_snapshot={
                    "channel_name": "신한 리서치",
                    "channel_message_id": "99",
                    "channel_key": "shinhan",
                },
                source_type="telegram",
            )
        ]
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "chunk 1234 신한 리서치#99" in markdown


def test_mixed_refs_both_sources_rendered() -> None:
    """텔레그램 + PDF 출처가 혼재할 때 양쪽 모두 렌더된다."""
    artifact = _make_artifact_with_refs(
        [
            ReportEvidenceRef(
                section_key="category_summaries",
                item_key="반도체",
                knowledge_chunk_id=1234,
                rank_score=1.0,
                knowledge_chunk_snapshot={
                    "channel_name": "신한",
                    "channel_message_id": "1",
                    "channel_key": "shinhan",
                },
                source_type="telegram",
            ),
            ReportEvidenceRef(
                section_key="category_summaries",
                item_key="반도체",
                rank_score=0.85,
                knowledge_chunk_snapshot={
                    "evidence_kind": "searched",
                    "doc_title": "리포트",
                    "broker_key": "kb",
                },
                source_type="pdf",
                document_chunk_id=9002,
            ),
        ]
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "chunk 1234" in markdown
    assert "doc 9002" in markdown


def test_parse_referenced_does_not_match_doc_format() -> None:
    """parse_referenced_from_markdown이 'doc {id}' 형식을 chunk id로 오인하지 않는다 (B3)."""
    from src.pipelines.stock_report.render_markdown import parse_referenced_from_markdown

    # 텔레그램 chunk 형식
    ids = parse_referenced_from_markdown("출처: chunk 1234 신한#99")
    assert 1234 in ids

    # PDF doc 형식 — 오인 금지
    pdf_ids = parse_referenced_from_markdown("출처: doc 9001 samsung · 반도체 전망")
    assert 9001 not in pdf_ids
