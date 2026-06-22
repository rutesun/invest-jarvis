from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from src.pipelines.stock_report.synthesize import (
    MINOR_CATEGORY_ITEM_KEY,
    ReportSectionItem,
    StockReportArtifact,
)


if TYPE_CHECKING:
    from src.pipelines.stock_report.google_grounding import GoogleGroundedArtifact


# Issue 2: Core Themes/category 출처 줄이 한 줄에 20여 개까지 나열돼 가독성을 해쳤다.
# 채널 단위로 dedup해 대표 1줄씩만 남기고 이 개수까지만 노출한다 (나머지는 '외 N건').
# 완전한 chunk 단위 출처는 DB report_evidence에 별도 영속되므로 표시 축약이 추적성을 해치지 않는다.
_MAX_SOURCES_SHOWN = 6


class MarkdownReportBuilder:
    def build(self, report: StockReportArtifact) -> str:
        source_lookup: dict[tuple[str, str], list[tuple[str, str]]] = self._build_source_lookup(
            report
        )
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

    def _build_source_lookup(
        self, report: StockReportArtifact
    ) -> dict[tuple[str, str], list[tuple[str, str]]]:
        """(section_key, item_key) -> ordered [(channel_name, display_line)].

        Exact-duplicate display lines are dropped here; channel-level dedup + capping happens
        at render time (see _format_sources) so the same lookup can feed every section.
        source_type dispatch: 'pdf' → 'doc {id} {broker} · {title}', else telegram format.
        """
        lookup: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        seen: dict[tuple[str, str], set[str]] = defaultdict(set)
        for ref in report.evidence_refs:
            snapshot = ref.knowledge_chunk_snapshot or {}
            if getattr(ref, "source_type", "telegram") == "pdf":
                broker = snapshot.get("broker_key") or "pdf"
                title = snapshot.get("doc_title") or ""
                doc_id = ref.document_chunk_id
                title_part = f" · {title}" if title else ""
                line = f"doc {doc_id} {broker}{title_part}"
                channel_name = broker
            else:
                channel_name = snapshot.get("channel_name") or snapshot.get("channel_key") or "unknown"
                channel_message_id = snapshot.get("channel_message_id") or "-"
                line = f"chunk {ref.knowledge_chunk_id} {channel_name}#{channel_message_id}"
            key = (ref.section_key, ref.item_key)
            if line not in seen[key]:
                seen[key].add(line)
                lookup[key].append((channel_name, line))
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
        source_lookup: dict[tuple[str, str], list[tuple[str, str]]],
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
                sources = [(f"chunk {cid}", f"chunk {cid}") for cid in item.evidence_chunk_ids]

            # 기타 단신 (issue 1): flat one-liner bullets, not the grouped card layout.
            if item.key == MINOR_CATEGORY_ITEM_KEY:
                lines.extend(self._render_minor_briefs(item, sources))
                continue

            lines.append(f"### {item.title}")
            for label, values in self._groups_for(kind, item, sources):
                # 출처 stays on a single line; channel-deduped + capped (see _format_sources).
                if label == "출처":
                    formatted = self._format_sources(values)
                    if formatted:
                        lines.append(f"- 출처: {formatted}")
                    continue
                clean = [str(v).strip() for v in values if v and str(v).strip()]
                if not clean:
                    continue
                lines.append(f"- {label}")
                lines.extend(f"  - {value}" for value in clean)
        return "\n".join(lines)

    def _format_sources(
        self, sources: list[tuple[str, str]], limit: int = _MAX_SOURCES_SHOWN
    ) -> str:
        """Collapse sources to one representative line per channel, rank by citation
        frequency (then first appearance), cap at ``limit``, and append '외 N건' for the
        remaining channels. Keeps the line readable while preserving one parseable
        ``chunk {id}`` token per shown channel."""
        first_line: dict[str, str] = {}
        counts: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for idx, (channel, line) in enumerate(sources):
            display = (line or "").strip()
            if not display:
                continue
            if channel not in first_line:
                first_line[channel] = display
                counts[channel] = 0
                first_seen[channel] = idx
            counts[channel] += 1
        if not first_line:
            return ""
        ranked = sorted(first_line, key=lambda c: (-counts[c], first_seen[c]))
        shown = ranked[:limit]
        text = ", ".join(first_line[c] for c in shown)
        remaining = len(ranked) - len(shown)
        if remaining > 0:
            text = f"{text} 외 {remaining}건"
        return text

    def _render_minor_briefs(
        self, item: ReportSectionItem, sources: list[tuple[str, str]]
    ) -> list[str]:
        """Flat one-liner layout for the consolidated '기타 단신' item (issue 1): each brief is a
        bullet directly under the heading, followed by the deduped 출처 line."""
        lines = [f"### {item.title}"]
        for bullet in item.evidence_bullets:
            text = str(bullet).strip()
            if text:
                lines.append(f"- {text}")
        formatted = self._format_sources(sources)
        if formatted:
            lines.append(f"- 출처: {formatted}")
        return lines

    def _groups_for(
        self, kind: str, item: ReportSectionItem, sources: list[tuple[str, str]]
    ) -> list[tuple[str, list[Any]]]:
        """Ordered (label, values) groups per section type. Empty groups are skipped
        by the caller, so a missing field simply omits its label.

        Most groups return ``list[str]`` values; the "출처" group returns
        ``list[tuple[str, str]]`` (channel, display_line) pairs consumed by
        ``_format_sources``. The heterogeneous value types are reflected in the
        ``list[Any]`` return annotation — callers must branch on label == "출처"
        before processing values (which ``render_section`` already does).
        """
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
        catalyst = (stock.get("catalyst") or "").strip()
        label = f"{name}({ticker})" if ticker and ticker != name else name
        # Raw-fallback / LLM-failure cards carry stocks with no catalyst; render just the
        # label instead of a dangling "라벨: -" (the empty-description noise from issue 1).
        return f"{label}: {catalyst}" if catalyst else label


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
    # H1 title matches the canonical T09-A report (MarkdownReportBuilder.build) so both
    # outputs share the same top-level layout.
    title = f"# Daily Stock Report V2 - {artifact.report_date.isoformat()}"
    banner = (
        f"> ⚠️ **[EXPERIMENTAL] Google Search Grounding 실험 경로** — {grounding_label}  \n"
        "> Phase 3 news corpus 도입 전 T09-A 기본 경로와 비교 목적으로만 사용하세요."
    )

    # Safety net: when grounding did not fire, the body is ungrounded Gemini output that
    # fabricates numbers/entities (e.g. clinical rates, FDA dates). Suppress it rather than
    # ship unverified figures — direct the reader to the T09-A report instead.
    if not artifact.grounding_active:
        notice = (
            "> ⚠️ Google Search Grounding이 발동하지 않아 검증되지 않은 본문 생성을 생략합니다. "
            "기본 경로(T09-A) 리포트를 사용하세요."
        )
        return "\n\n".join([title, banner, notice]).rstrip() + "\n"

    parts = [
        title,
        banner,
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
