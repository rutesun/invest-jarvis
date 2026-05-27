from __future__ import annotations

from src.pipelines.stock_report.synthesize import ReportSectionItem, StockReportArtifact


class MarkdownReportBuilder:
    def build(self, report: StockReportArtifact) -> str:
        parts = [
            f"# Daily Stock Report V2 - {report.report_date.isoformat()}",
            "",
            self.render_pulse(report.pulse),
            self.render_items("Category Summaries", report.category_summaries),
            self.render_items("Core Themes", report.core_themes),
            self.render_items("Focus Tickers", report.focus_tickers),
            self.render_notes(report.low_confidence_notes),
        ]
        return "\n\n".join(part for part in parts if part.strip()).rstrip() + "\n"

    def render_pulse(self, pulse: list[str]) -> str:
        lines = ["## Pulse"]
        lines.extend(f"- {item}" for item in pulse)
        return "\n".join(lines)

    def render_items(self, title: str, items: list[ReportSectionItem]) -> str:
        lines = [f"## {title}"]
        if not items:
            lines.append("- 해당 항목 없음")
            return "\n".join(lines)

        for item in items:
            lines.append(f"### {item.title}")
            lines.append(item.body)
            if item.evidence_chunk_ids:
                ids = ", ".join(str(chunk_id) for chunk_id in item.evidence_chunk_ids)
                lines.append(f"- 근거 chunk: `{ids}`")
        return "\n".join(lines)

    def render_notes(self, notes: list[str]) -> str:
        lines = ["## Low Confidence"]
        if not notes:
            lines.append("- 해당 항목 없음")
            return "\n".join(lines)
        lines.extend(f"- {note}" for note in notes)
        return "\n".join(lines)


def render_stock_report_markdown(report: StockReportArtifact) -> str:
    return MarkdownReportBuilder().build(report)
