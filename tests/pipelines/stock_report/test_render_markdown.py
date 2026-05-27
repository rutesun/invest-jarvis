from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.render_markdown import MarkdownReportBuilder
from src.pipelines.stock_report.synthesize import (
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
    assert "- 근거: NVDA HBM 수요 증가" in markdown
    assert "- Impact: 반도체 업황 회복 기대가 강화된다" in markdown
    assert "- 관련 종목: 엔비디아(NVDA): HBM 수요" in markdown
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

    assert "- 관련 종목: 삼전닉스: 2배 레버리지 상품 출시" in markdown
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

    assert "- 관련 종목: 삼성전자: 레버리지 ETF 출시" in markdown
    assert "삼성전자(삼성전자)" not in markdown


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

    assert "- 핵심 주장: AI CAPEX가 GPU를 넘어 HBM, 전력, 커패시터로 확산 중이다." in markdown
    assert "- 근거: ADI 데이터센터 매출이 통신 부문의 75%" in markdown
    assert "- Impact: AI 수혜가 엔비디아 중심에서 부품·전력·메모리로 넓어진다." in markdown
    assert "- 확인 변수: 빅테크 CAPEX 지속성, 메모리 가격 상승 지속 여부" in markdown
    assert "- 연결 카테고리: AI인프라, 반도체, 원전/전력인프라" in markdown


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

    assert "- 투자 포인트: HBM 수요와 ETF 수급이 동시에 붙는 대표 수혜주다." in markdown
    assert "- 촉매: iHBM 냉각 솔루션 공개, 단일종목 레버리지 ETF 출시" in markdown
    assert "- 핵심 수치: 주가 5.72% 급등, 열 저항 30% 감소" in markdown
    assert "- 근거: 주가 5.72% 급등" in markdown
    assert "- 리스크/확인: ETF 출시 후 차익실현, HBM 공급 경쟁 심화" in markdown
    assert "- 관련 테마: HBM, 반도체 레버리지 ETF" in markdown
