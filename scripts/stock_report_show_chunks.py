#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.pipelines.stock_report.db import connect_db, resolve_db_dsn


@dataclass(slots=True)
class ChunkRow:
    chunk_id: int
    source_pk: int | None
    posted_at: datetime | None
    channel_key: str | None
    channel_message_id: str | None
    message_type: str
    event_type: str | None
    category_key: str
    main_theme: str | None
    sub_themes: list[str]
    ticker_tags: list[str]
    canonical_summary: str
    supporting_facts: list[str]
    evidence_items: list[dict[str, Any]]
    qa_warnings: list[dict[str, Any]]
    provisional_category: str | None
    provisional_theme: str | None
    is_provisional: bool
    content_clean: str
    raw_text: str


def _parse_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            loaded = json.loads(stripped)
            if isinstance(loaded, list):
                return [str(item) for item in loaded]
        except json.JSONDecodeError:
            return [stripped]
    return [str(value)]


def _parse_json_objects(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    loaded: Any = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def _group_evidence_by_kind(evidence_items: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in evidence_items:
        kind = str(item.get("kind") or "fact")
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        grouped.setdefault(kind, []).append(text)
    return grouped


def _count_warning_codes(chunks: list[ChunkRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        for warning in chunk.qa_warnings:
            code = str(warning.get("code") or "-")
            counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _taxonomy_issue_summary(chunks: list[ChunkRow]) -> tuple[str, str] | None:
    unclassified_count = 0
    provisional_fields_count = 0
    mismatch_count = 0
    samples: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        has_provisional = bool(chunk.provisional_category or chunk.provisional_theme)
        is_unclassified = chunk.category_key == "unclassified"
        is_mismatch = chunk.category_key != "unclassified" and has_provisional
        if is_unclassified:
            unclassified_count += 1
        if has_provisional:
            provisional_fields_count += 1
        if is_mismatch:
            mismatch_count += 1
        if not (is_unclassified or has_provisional):
            continue
        samples.append(
            f"u{idx}(cat={chunk.category_key}, main={chunk.main_theme or '-'}, "
            f"prov_cat={chunk.provisional_category or '-'}, "
            f"prov_theme={chunk.provisional_theme or '-'}, "
            f"is_provisional={chunk.is_provisional})"
        )
    if not samples:
        return None
    summary = (
        "unclassified="
        f"{unclassified_count}, provisional_fields={provisional_fields_count}, "
        f"category_provisional_mismatch={mismatch_count}"
    )
    return summary, "; ".join(samples[:3])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show stock_report knowledge_chunks grouped by message(source_pk)."
    )
    parser.add_argument("date", help="조회 날짜 (YYYY-MM-DD)")
    parser.add_argument(
        "--dsn",
        default=None,
        help="DB DSN (미지정 시 STOCK_REPORT_DB_DSN 또는 DATABASE_URL 사용)",
    )
    parser.add_argument(
        "--source-type",
        default="telegram_unit_v2",
        help="knowledge_chunks.source_type 필터 (기본: telegram_unit_v2)",
    )
    parser.add_argument(
        "--channel-key",
        action="append",
        default=[],
        help="특정 채널만 조회 (여러 번 지정 가능). 예: --channel-key ked_epic_ai",
    )
    return parser.parse_args()


def load_chunks(
    conn: Any,
    *,
    date: str,
    source_type: str,
    channel_keys: list[str],
) -> list[ChunkRow]:
    filters = [
        "kc.source_date = %s",
        "kc.source_type = %s",
    ]
    params: list[Any] = [date, source_type]
    if channel_keys:
        filters.append("COALESCE(kc.channel_key, tm.channel_key) = ANY(%s)")
        params.append(channel_keys)

    query = """
    SELECT
        kc.id,
        kc.source_pk,
        tm.posted_at,
        COALESCE(kc.channel_key, tm.channel_key) AS channel_key,
        tm.channel_message_id,
        kc.message_type,
        kc.event_type,
        kc.category_key,
        kc.main_theme,
        kc.sub_themes,
        kc.ticker_tags,
        kc.canonical_summary,
        kc.supporting_facts,
        kc.evidence_items,
        kc.qa_warnings,
        kc.provisional_category,
        kc.provisional_theme,
        kc.is_provisional,
        kc.content_clean,
        COALESCE(tm.raw_text, '')
    FROM knowledge_chunks kc
    LEFT JOIN telegram_messages tm
        ON tm.id = kc.source_pk
    WHERE {where_clause}
    ORDER BY kc.source_pk NULLS LAST, kc.id ASC;
    """.format(where_clause=" AND ".join(filters))
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    result: list[ChunkRow] = []
    for row in rows:
        result.append(
            ChunkRow(
                chunk_id=int(row[0]),
                source_pk=int(row[1]) if row[1] is not None else None,
                posted_at=row[2],
                channel_key=row[3],
                channel_message_id=row[4],
                message_type=str(row[5]),
                event_type=row[6],
                category_key=str(row[7]),
                main_theme=row[8],
                sub_themes=_parse_json_list(row[9]),
                ticker_tags=_parse_json_list(row[10]),
                canonical_summary=str(row[11]),
                supporting_facts=_parse_json_list(row[12]),
                evidence_items=_parse_json_objects(row[13]),
                qa_warnings=_parse_json_objects(row[14]),
                provisional_category=row[15],
                provisional_theme=row[16],
                is_provisional=bool(row[17]),
                content_clean=str(row[18] or ""),
                raw_text=str(row[19] or ""),
            )
        )
    return result


def render_grouped(chunks: list[ChunkRow]) -> str:
    if not chunks:
        return "No chunks found."

    grouped: dict[int | None, list[ChunkRow]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.source_pk].append(chunk)

    lines: list[str] = []
    lines.append("# Knowledge Chunks")
    lines.append(f"- total chunks: {len(chunks)}")
    lines.append(f"- grouped messages: {len(grouped)}")
    lines.append("")

    for source_pk in sorted(grouped, key=lambda x: (x is None, x)):
        items = grouped[source_pk]
        head = items[0]
        source_label = str(source_pk) if source_pk is not None else "null-source"
        lines.append(
            f"## message {source_label} "
            f"({head.channel_key or '-'}#{head.channel_message_id or '-'}) "
            f"[{len(items)} summaries]"
        )
        if head.posted_at is not None:
            lines.append(f"- posted_at: {head.posted_at.isoformat()}")
        preview = (head.raw_text or head.content_clean).strip()
        preview_lines = preview.splitlines()
        if not preview_lines:
            lines.append("- content_preview: -")
        else:
            lines.append("- content_preview:")
            for line in preview_lines:
                lines.append(f"  {line}")
        lines.append(f"- message_qa.warning_counts: {_count_warning_codes(items)}")
        taxonomy_summary = _taxonomy_issue_summary(items)
        if taxonomy_summary:
            taxonomy_counts, taxonomy_samples = taxonomy_summary
            lines.append(f"- message_qa.taxonomy: {taxonomy_counts}")
            lines.append(f"- message_qa.taxonomy_samples: {taxonomy_samples}")
        lines.append("")

        for idx, item in enumerate(items, start=1):
            sub = ", ".join(item.sub_themes) if item.sub_themes else "-"
            tickers = ", ".join(item.ticker_tags) if item.ticker_tags else "-"
            facts = " | ".join(item.supporting_facts[:3]) if item.supporting_facts else "-"
            warnings = (
                " | ".join(
                    (
                        f"{entry.get('code')}: {entry.get('detail')}"
                        if entry.get("detail")
                        else str(entry.get("code"))
                    )
                    for entry in item.qa_warnings
                )
                if item.qa_warnings
                else "-"
            )
            lines.append(f"- summary {idx}: {item.canonical_summary}")
            lines.append(
                f"  - type: {item.message_type}"
                + (f" / {item.event_type}" if item.event_type else "")
            )
            lines.append(f"  - category: {item.category_key}")
            lines.append(f"  - theme: main={item.main_theme or '-'} / sub={sub}")
            lines.append(
                "  - provisional: "
                f"category={item.provisional_category or '-'}, "
                f"theme={item.provisional_theme or '-'}, "
                f"is_provisional={item.is_provisional}"
            )
            lines.append(f"  - tickers: {tickers}")
            grouped_evidence = _group_evidence_by_kind(item.evidence_items)
            if grouped_evidence:
                for kind, evidence_texts in grouped_evidence.items():
                    lines.append(f"  - evidence_items.{kind}: {' | '.join(evidence_texts[:5])}")
            else:
                lines.append("  - evidence_items: -")
            lines.append(f"  - supporting_facts: {facts}")
            lines.append(f"  - qa_warnings: {warnings}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    dsn = resolve_db_dsn(args.dsn)
    with connect_db(dsn) as conn:
        chunks = load_chunks(
            conn,
            date=args.date,
            source_type=args.source_type,
            channel_keys=args.channel_key,
        )
    print(render_grouped(chunks))


if __name__ == "__main__":
    main()
