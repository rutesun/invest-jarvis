"""Stock Report V2 evaluation harness (T09-I).

Two-track usage:
- Track 1 (golden set): run against frozen fixture bundles for prompt-tuning
  regression (deterministic coverage in CI; faithfulness on demand with real LLM).
- Track 2 (same-day live): run against today's real report as a DRIFT DETECTOR,
  not a release gate. Newly surfaced misses get human-reviewed then promoted into
  the golden-set must-have checklist (reuses the weekly tuning.py review loop).

Metrics:
- coverage: per-category referenced/total chunks. Denominator = deduped same-day
  synthesis chunks (post build_same_day_bundle), NOT the raw message count.
  Flags categories with >= MIN_SIGNAL_FOR_FLAG signal chunks and 0 referenced.
- faithfulness (LLM judge, recall framing — not a holistic score):
  * missing_events: distinct events in the chunks absent from the report.
  * hallucinated_claims: report statements not grounded in any chunk.

Usage:
    uv run python scripts/stock_report_eval.py 2026-05-28
    uv run python scripts/stock_report_eval.py 2026-05-28 --markdown reports/2026-05/daily_v2_2026-05-28.google.md
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.pipelines.stock_report.db import connect_db, resolve_db_dsn
from src.pipelines.stock_report.retrieval import SameDayBundle, load_same_day_bundle


MIN_SIGNAL_FOR_FLAG = 3

# chunk ids appear as "[2884]" (T09-A) or "chunk 2884" (T09-B google) in rendered reports
_CHUNK_ID_PATTERNS = (re.compile(r"\[(\d{3,6})\]"), re.compile(r"chunk\s+(\d{3,6})"))


@dataclass(slots=True)
class CategoryCoverage:
    category: str
    total: int
    signal_total: int
    referenced: int
    missing: bool  # signal_total >= MIN_SIGNAL_FOR_FLAG and referenced == 0


@dataclass(slots=True)
class CoverageReport:
    report_date: str
    denominator: int  # deduped synthesis chunks
    referenced_total: int
    coverage_rate: float
    categories: list[CategoryCoverage]
    missing_categories: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FaithfulnessReport:
    missing_events: list[str]
    hallucinated_claims: list[str]


# ---------------------------------------------------------------------------
# Coverage (deterministic, pure)
# ---------------------------------------------------------------------------


def compute_coverage(bundle: SameDayBundle, referenced_ids: set[int]) -> CoverageReport:
    """Per-category referenced/total against the deduped same-day bundle."""
    categories: list[CategoryCoverage] = []
    missing: list[str] = []
    referenced_total = 0
    denominator = 0

    for bucket in bundle.category_buckets:
        total = len(bucket.chunks)
        signal_total = sum(1 for c in bucket.chunks if c.message_type == "signal")
        referenced = sum(1 for c in bucket.chunks if c.id in referenced_ids)
        denominator += total
        referenced_total += referenced
        is_missing = signal_total >= MIN_SIGNAL_FOR_FLAG and referenced == 0
        if is_missing:
            missing.append(bucket.category_key)
        categories.append(
            CategoryCoverage(
                category=bucket.category_key,
                total=total,
                signal_total=signal_total,
                referenced=referenced,
                missing=is_missing,
            )
        )

    rate = (referenced_total / denominator) if denominator else 0.0
    return CoverageReport(
        report_date=bundle.report_date.isoformat(),
        denominator=denominator,
        referenced_total=referenced_total,
        coverage_rate=rate,
        categories=categories,
        missing_categories=missing,
    )


def parse_referenced_from_markdown(text: str) -> set[int]:
    """Extract referenced chunk ids from a rendered report (T09-A [id] or T09-B 'chunk id')."""
    ids: set[int] = set()
    for pattern in _CHUNK_ID_PATTERNS:
        for match in pattern.finditer(text):
            ids.add(int(match.group(1)))
    return ids


def load_referenced_from_db(conn: Any, report_date: str) -> set[int]:
    """Referenced chunk ids from the latest report_run's report_evidence for a date."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM report_runs WHERE report_date = %s ORDER BY created_at DESC LIMIT 1",
        (report_date,),
    )
    row = cur.fetchone()
    if not row:
        return set()
    run_id = row[0]
    cur.execute(
        "SELECT DISTINCT knowledge_chunk_id FROM report_evidence WHERE report_run_id = %s",
        (run_id,),
    )
    return {r[0] for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# Faithfulness (LLM judge — recall framing, injectable for tests)
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "너는 리포트 검증기다. 주어진 evidence 청크 요약과 리포트 본문을 비교해 두 가지만 한다: "
    "(1) 청크에 있으나 리포트에 빠진 distinct 사건(missing_events), "
    "(2) 리포트에 있으나 어떤 청크에도 근거가 없는 주장(hallucinated_claims). "
    "좋고 나쁨을 점수 매기지 말고 위 두 리스트만 JSON으로 반환하라."
)

JudgeCall = Callable[[str, str], dict[str, Any]]


def _build_judge_user_prompt(report_markdown: str, chunk_summaries: list[str]) -> str:
    facts = "\n".join(f"- {s}" for s in chunk_summaries)
    return (
        f"evidence 청크 요약:\n{facts}\n\n"
        f"리포트 본문:\n{report_markdown}\n\n"
        '{"missing_events": [...], "hallucinated_claims": [...]} 형태 JSON만 반환.'
    )


def judge_faithfulness(
    report_markdown: str,
    chunk_summaries: list[str],
    *,
    judge_call: JudgeCall,
) -> FaithfulnessReport:
    """Run the recall-based faithfulness judge. judge_call is injected for testability."""
    user = _build_judge_user_prompt(report_markdown, chunk_summaries)
    result = judge_call(_JUDGE_SYSTEM, user)
    return FaithfulnessReport(
        missing_events=[str(x) for x in result.get("missing_events", [])],
        hallucinated_claims=[str(x) for x in result.get("hallucinated_claims", [])],
    )


def _default_judge_call(system: str, user: str) -> dict[str, Any]:
    """Real LLM judge via the report synthesis provider (used by the CLI)."""
    from src.pipelines.stock_report.config import get_report_synthesis_llm_config

    llm = get_report_synthesis_llm_config("openai").create_llm()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    response = llm.invoke(messages)
    text = response.content if hasattr(response, "content") else str(response)
    return json.loads(_strip_fence(str(text)))


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = next((i + 1 for i, line in enumerate(lines) if line.startswith("```")), 1)
        end = next(
            (i for i in range(len(lines) - 1, start, -1) if lines[i].startswith("```")),
            len(lines),
        )
        return "\n".join(lines[start:end])
    return text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _render_coverage(cov: CoverageReport) -> str:
    lines = [
        f"# Coverage — {cov.report_date}",
        f"- deduped synthesis chunks (denominator): {cov.denominator}",
        f"- referenced: {cov.referenced_total}  ({cov.coverage_rate:.1%})",
        "",
        "| category | total | signal | referenced | flag |",
        "|---|---|---|---|---|",
    ]
    for c in cov.categories:
        flag = "MISSING" if c.missing else ""
        lines.append(f"| {c.category} | {c.total} | {c.signal_total} | {c.referenced} | {flag} |")
    if cov.missing_categories:
        lines.append("")
        lines.append(
            f"FAIL: {len(cov.missing_categories)} category(s) with signal>=3 and 0 refs: "
            + ", ".join(cov.missing_categories)
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stock Report V2 eval harness (coverage + faithfulness)"
    )
    parser.add_argument("date", help="report date YYYY-MM-DD")
    parser.add_argument(
        "--markdown", help="report .md to parse refs from (default: read DB report_evidence)"
    )
    parser.add_argument("--dsn", default=None, help="DB DSN override")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of table")
    args = parser.parse_args(argv)

    dsn = resolve_db_dsn(args.dsn)
    with connect_db(dsn) as conn:
        bundle = load_same_day_bundle(conn, args.date)
        if args.markdown:
            with open(args.markdown, encoding="utf-8") as f:
                referenced = parse_referenced_from_markdown(f.read())
        else:
            referenced = load_referenced_from_db(conn, args.date)

    cov = compute_coverage(bundle, referenced)

    if args.json:
        print(json.dumps(cov, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))
    else:
        print(_render_coverage(cov))
    return 1 if cov.missing_categories else 0


if __name__ == "__main__":
    raise SystemExit(main())
