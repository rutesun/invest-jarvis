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
import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.pipelines.stock_report.db import connect_db, resolve_db_dsn
from src.pipelines.stock_report.render_markdown import parse_referenced_from_markdown
from src.pipelines.stock_report.retrieval import SameDayBundle, load_same_day_bundle


MIN_SIGNAL_FOR_FLAG = 3


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
    response = asyncio.run(llm.ainvoke(messages))
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
# Golden set (curated must-have events) — same fixtures power the hermetic pytest
# regression (tests/pipelines/stock_report/test_golden_set.py) and this live-drift check
# against a rendered report. Fixtures are hand-maintained static JSON (format documented
# in test_golden_set.py); no DB is involved.
# ---------------------------------------------------------------------------

GOLDEN_DIR = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "stock_report" / "golden"
)


def load_golden_must_haves(report_date: str) -> list[dict[str, Any]]:
    """Load curated must-have events for a date; [] if no fixture exists."""
    path = GOLDEN_DIR / f"{report_date}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("must_have_events", []))


def check_golden_coverage(report_markdown: str, must_haves: list[dict[str, Any]]) -> list[str]:
    """Return descriptions of must-have events absent from the rendered report.

    An event is present when ANY of its match_any substrings appears in the report text.
    """
    missing: list[str] = []
    for event in must_haves:
        substrings = event.get("match_any") or []
        if not any(s in report_markdown for s in substrings):
            missing.append(event.get("description", "(no description)"))
    return missing


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
    parser.add_argument(
        "--golden",
        action="store_true",
        help="check the rendered report (requires --markdown) against the curated golden "
        "must-have events for the date",
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv()
    dsn = resolve_db_dsn(args.dsn)
    report_text = ""
    with connect_db(dsn) as conn:
        bundle = load_same_day_bundle(conn, args.date)
        if args.markdown:
            with open(args.markdown, encoding="utf-8") as f:
                report_text = f.read()
            referenced = parse_referenced_from_markdown(report_text)
        else:
            referenced = load_referenced_from_db(conn, args.date)

    cov = compute_coverage(bundle, referenced)

    if args.json:
        # asdict recurses into the nested CategoryCoverage list; slots dataclasses have
        # no __dict__, so the previous default=lambda o: o.__dict__ always crashed here.
        print(json.dumps(asdict(cov), ensure_ascii=False, indent=2))
    else:
        print(_render_coverage(cov))

    golden_missing: list[str] = []
    if args.golden:
        must_haves = load_golden_must_haves(args.date)
        if not must_haves:
            print(f"\n[golden] {args.date}: no fixture at {GOLDEN_DIR / f'{args.date}.json'}")
        elif not report_text:
            print("\n[golden] requires --markdown to check the rendered report")
        else:
            golden_missing = check_golden_coverage(report_text, must_haves)
            present = len(must_haves) - len(golden_missing)
            print(f"\n# Golden must-haves — {args.date}: {present}/{len(must_haves)} present")
            for desc in golden_missing:
                print(f"  MISSING: {desc}")

    return 1 if (cov.missing_categories or golden_missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
