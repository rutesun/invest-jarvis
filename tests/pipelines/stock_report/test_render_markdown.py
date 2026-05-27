from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.render_markdown import MarkdownReportBuilder
from src.pipelines.stock_report.synthesize import ReportSectionItem, StockReportArtifact


def test_markdown_report_builder_renders_fixed_sections() -> None:
    artifact = StockReportArtifact(
        report_date=date(2026, 5, 26),
        pulse=["오늘은 반도체와 자동차가 핵심 축이었다."],
        category_summaries=[
            ReportSectionItem(
                key="반도체",
                title="반도체",
                body="NVDA HBM 수요가 강하다",
                evidence_chunk_ids=[1],
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
        evidence_refs=[],
    )

    markdown = MarkdownReportBuilder().build(artifact)

    assert "# Daily Stock Report V2 - 2026-05-26" in markdown
    assert "## Pulse" in markdown
    assert "## Category Summaries" in markdown
    assert "## Core Themes" in markdown
    assert "## Focus Tickers" in markdown
    assert "## Low Confidence" in markdown
    assert "근거 chunk: `1`" in markdown
