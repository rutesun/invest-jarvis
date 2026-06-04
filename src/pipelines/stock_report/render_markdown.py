from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from src.pipelines.stock_report.synthesize import ReportSectionItem, StockReportArtifact


if TYPE_CHECKING:
    from src.pipelines.stock_report.google_grounding import GoogleGroundedArtifact


class MarkdownReportBuilder:
    def build(self, report: StockReportArtifact) -> str:
        source_lookup = self._build_source_lookup(report)
        parts = [
            f"# Daily Stock Report V2 - {report.report_date.isoformat()}",
            "",
            self.render_pulse(report.pulse),
            self.render_items("Category Summaries", report.category_summaries, source_lookup),
            self.render_items("Core Themes", report.core_themes, source_lookup),
            self.render_items("Focus Tickers", report.focus_tickers, source_lookup),
            self.render_notes(report.low_confidence_notes),
        ]
        return "\n\n".join(part for part in parts if part.strip()).rstrip() + "\n"

    def _build_source_lookup(self, report: StockReportArtifact) -> dict[tuple[str, str], list[str]]:
        lookup: dict[tuple[str, str], list[str]] = defaultdict(list)
        for ref in report.evidence_refs:
            snapshot = ref.knowledge_chunk_snapshot or {}
            channel_name = snapshot.get("channel_name") or snapshot.get("channel_key") or "unknown"
            channel_message_id = snapshot.get("channel_message_id") or "-"
            line = f"chunk {ref.knowledge_chunk_id} {channel_name}#{channel_message_id}"
            key = (ref.section_key, ref.item_key)
            if line not in lookup[key]:
                lookup[key].append(line)
        return lookup

    def render_pulse(self, pulse: list[ReportSectionItem]) -> str:
        lines = ["## Pulse"]
        lines.extend(f"- {item.title}: {item.body}" for item in pulse)
        return "\n".join(lines)

    def render_items(
        self,
        title: str,
        items: list[ReportSectionItem],
        source_lookup: dict[tuple[str, str], list[str]],
    ) -> str:
        lines = [f"## {title}"]
        if not items:
            lines.append("- 해당 항목 없음")
            return "\n".join(lines)

        section_key = title.lower().replace(" ", "_")
        for item in items:
            lines.append(f"### {item.title}")
            if item.investment_case:
                lines.append(f"- 투자 포인트: {item.investment_case}")
            if item.catalysts:
                lines.append(f"- 촉매: {', '.join(item.catalysts)}")
            if item.key_metrics:
                lines.append(f"- 핵심 수치: {', '.join(item.key_metrics)}")
            if item.thesis:
                lines.append(f"- 핵심 주장: {item.thesis}")
            if item.evidence_bullets:
                lines.extend(f"- {bullet}" for bullet in item.evidence_bullets)
            elif item.body and item.body not in (item.thesis, item.investment_case):
                lines.append(item.body)

            if item.impact:
                lines.append(f"- **Impact:** {item.impact}")
            if item.watch_points:
                lines.append(f"- 확인 변수: {', '.join(item.watch_points)}")
            if item.risks_or_watch_points:
                lines.append(f"- 리스크/확인: {', '.join(item.risks_or_watch_points)}")
            if item.related_categories:
                lines.append(f"- 연결 카테고리: {', '.join(item.related_categories)}")
            if item.related_themes:
                lines.append(f"- 관련 테마: {', '.join(item.related_themes)}")
            if item.related_stocks:
                lines.extend(
                    f"- 관련 종목: {self._format_related_stock(stock)}"
                    for stock in item.related_stocks
                )

            sources = source_lookup.get((section_key, item.key), [])
            if not sources and item.evidence_chunk_ids:
                sources = [f"chunk {chunk_id}" for chunk_id in item.evidence_chunk_ids]
            if sources:
                lines.append(f"- 출처: {', '.join(sources)}")
        return "\n".join(lines)

    def render_notes(self, notes: list[str]) -> str:
        lines = ["## Low Confidence"]
        if not notes:
            lines.append("- 해당 항목 없음")
            return "\n".join(lines)
        lines.extend(f"- {note}" for note in notes)
        return "\n".join(lines)

    def _format_related_stock(self, stock: dict[str, str | None]) -> str:
        name = stock.get("name") or "-"
        ticker = stock.get("ticker")
        catalyst = stock.get("catalyst") or "-"
        label = f"{name}({ticker})" if ticker and ticker != name else name
        return f"{label}: {catalyst}"


def render_stock_report_markdown(report: StockReportArtifact) -> str:
    return MarkdownReportBuilder().build(report)


def render_google_grounded_report(artifact: GoogleGroundedArtifact) -> str:
    grounding_label = (
        "✓ Grounding 활성" if artifact.grounding_active else "✗ Grounding 미발동 (fallback)"
    )
    parts = [
        # H1 title matches the canonical T09-A report (MarkdownReportBuilder.build) so both
        # outputs share the same top-level layout.
        f"# Daily Stock Report V2 - {artifact.report_date.isoformat()}",
        f"> ⚠️ **[EXPERIMENTAL] Google Search Grounding 실험 경로** — {grounding_label}  \n"
        "> Phase 3 news corpus 도입 전 T09-A 기본 경로와 비교 목적으로만 사용하세요.",
        artifact.synthesis_markdown.rstrip(),
    ]

    if artifact.citations:
        citation_lines = ["---", "## 검색 출처 (Google Search Grounding)"]
        for citation in artifact.citations:
            label = citation.title or citation.uri
            citation_lines.append(f"[{citation.index}] [{label}]({citation.uri})")
        parts.append("\n".join(citation_lines))

    if artifact.search_queries:
        query_lines = ["## 검색 쿼리"]
        query_lines.extend(f"- {q}" for q in artifact.search_queries)
        parts.append("\n".join(query_lines))

    return "\n\n".join(parts).rstrip() + "\n"
