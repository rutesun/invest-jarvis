from __future__ import annotations

import re
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
            self.render_section(
                "Category Summaries", "category", report.category_summaries, source_lookup
            ),
            self.render_section("Core Themes", "theme", report.core_themes, source_lookup),
            self.render_section("Focus Tickers", "ticker", report.focus_tickers, source_lookup),
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
        for item in pulse:
            lines.append(f"- {item.title}")
            body = (item.body or "").strip()
            if body:
                lines.append(f"  - {body}")
        return "\n".join(lines)

    def render_section(
        self,
        title: str,
        kind: str,
        items: list[ReportSectionItem],
        source_lookup: dict[tuple[str, str], list[str]],
    ) -> str:
        """Render a section as grouped/nested bullets: each field is a labeled group
        with its content indented beneath it (same layout across category/theme/ticker)."""
        lines = [f"## {title}"]
        if not items:
            lines.append("- 해당 항목 없음")
            return "\n".join(lines)

        section_key = title.lower().replace(" ", "_")
        for item in items:
            sources = source_lookup.get((section_key, item.key), [])
            if not sources and item.evidence_chunk_ids:
                sources = [f"chunk {chunk_id}" for chunk_id in item.evidence_chunk_ids]

            lines.append(f"### {item.title}")
            for label, values in self._groups_for(kind, item, sources):
                clean = [str(v).strip() for v in values if v and str(v).strip()]
                if not clean:
                    continue
                # 출처 stays on a single comma-separated line; other fields nest.
                if label == "출처":
                    lines.append(f"- 출처: {', '.join(clean)}")
                    continue
                lines.append(f"- {label}")
                lines.extend(f"  - {value}" for value in clean)
        return "\n".join(lines)

    def _groups_for(
        self, kind: str, item: ReportSectionItem, sources: list[str]
    ) -> list[tuple[str, list[str]]]:
        """Ordered (label, values) groups per section type. Empty groups are skipped
        by the caller, so a missing field simply omits its label."""
        if kind == "category":
            related = ", ".join(item.related_categories) if item.related_categories else ""
            themes = ", ".join(item.related_themes) if item.related_themes else ""
            return [
                ("Narrative", [item.body]),
                ("Impact", [item.impact or ""]),
                ("근거", list(item.evidence_bullets)),
                ("관련 종목", [self._format_related_stock(s) for s in item.related_stocks]),
                ("연결 카테고리", [related]),
                ("관련 테마", [themes]),
                ("출처", sources),
            ]
        if kind == "theme":
            related = ", ".join(item.related_categories) if item.related_categories else ""
            return [
                ("핵심 주장", [item.thesis or item.body]),
                ("Impact", [item.impact or ""]),
                ("확인 변수", list(item.watch_points)),
                ("연결 카테고리", [related]),
                ("출처", sources),
            ]
        if kind == "ticker":
            return [
                ("투자 포인트", [item.investment_case or item.body]),
                ("촉매", list(item.catalysts)),
                ("핵심 수치", list(item.key_metrics)),
                ("리스크/확인", list(item.risks_or_watch_points)),
                ("출처", sources),
            ]
        return [("출처", sources)]

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


# ---------------------------------------------------------------------------
# Chunk-id reference parsing — inverse of the rendered "chunk {id}" source lines.
# Lives here next to the renderer so the wire format and its parser change together.
# ---------------------------------------------------------------------------

# chunk ids appear as "[2884]" (T09-A) or "chunk 2884" (T09-B google) in rendered reports
_CHUNK_ID_PATTERNS = (re.compile(r"\[(\d{3,6})\]"), re.compile(r"chunk\s+(\d{3,6})"))


def parse_referenced_from_markdown(text: str) -> set[int]:
    """Extract referenced chunk ids from a rendered report (T09-A [id] or T09-B 'chunk id')."""
    ids: set[int] = set()
    for pattern in _CHUNK_ID_PATTERNS:
        for match in pattern.finditer(text):
            ids.add(int(match.group(1)))
    return ids


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
