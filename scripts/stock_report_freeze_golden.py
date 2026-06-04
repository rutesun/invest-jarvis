"""Freeze a curated golden set of high-impact must-have events for regression tests.

Why content-based, not id-based: the daily-v2 pipeline re-extracts and re-ingests
knowledge_chunks on every run, so chunk ids are NOT stable across runs. The golden
fixtures therefore capture chunk *content* (canonical_summary, supporting_facts,
event_type, ...) so the resulting regression test is hermetic — it neither touches the
DB nor depends on id stability.

The curated manifest below lists the events a human analyst insists must never silently
drop from a daily briefing. Each entry is pinned to a current chunk id only to capture
its content at freeze time; a sanity check fails loudly if that id's summary no longer
contains the expected substrings (guards against grabbing the wrong chunk).

Usage:
    uv run python scripts/stock_report_freeze_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.pipelines.stock_report.db import connect_db, resolve_db_dsn


# date -> list of (chunk_id_at_freeze_time, description, match_any substrings)
CURATED_MUST_HAVES: dict[str, list[tuple[int, str, list[str]]]] = {
    "2026-06-02": [
        (3502, "MGM 인수 제안 (주당 48.30달러 현금)", ["MGM"]),
        (3508, "우버, 딜리버리히어로 잔여 지분 인수 제안", ["딜리버리", "우버"]),
        (3494, "한미약품-릴리 1.9조원 기술이전 계약", ["한미약품", "릴리"]),
        (3557, "퍼페추아 리소스 29억달러 프로젝트 대출", ["퍼페추아"]),
        (3559, "블랙스톤 아시아 사모펀드 131억달러 모집", ["블랙스톤"]),
        (3549, "앤트로픽 IPO 투자설명서 비공개 제출", ["앤트로픽"]),
        (3548, "알파벳 AI 인프라용 800억달러 증자 추진", ["알파벳", "800억"]),
    ],
    "2026-05-28": [
        (3718, "우버, 딜리버리히어로 지분 36.83% 확대·인수 가능성", ["딜리버리", "우버"]),
        (3638, "네비우스 헤지펀드 지분 5.6% 공시·시간외 급등", ["네비우스"]),
        (3745, "시놉시스 이사진에 엘리엇 매니지먼트 지명 인사 합류", ["시놉시스", "엘리엇"]),
        (3651, "프로로지움 TDAC와 38억달러 SPAC 합병·나스닥 상장", ["로지움"]),
    ],
}

FIXTURE_DIR = Path("tests/fixtures/stock_report/golden")


def _freeze_chunk(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "canonical_summary": row[0],
        "supporting_facts": list(row[1] or []),
        "event_type": row[2],
        "category_key": row[3],
        "priority_score": float(row[4]),
    }


def main() -> int:
    load_dotenv()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db(resolve_db_dsn()) as conn:
        cur = conn.cursor()
        for report_date, entries in CURATED_MUST_HAVES.items():
            must_have_events: list[dict[str, Any]] = []
            for chunk_id, description, match_any in entries:
                cur.execute(
                    "SELECT canonical_summary, supporting_facts, event_type, category_key, "
                    "priority_score FROM knowledge_chunks WHERE id = %s",
                    (chunk_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise SystemExit(f"[{report_date}] chunk id {chunk_id} not found")
                summary = row[0] or ""
                missing = [s for s in match_any if s not in summary]
                if missing:
                    raise SystemExit(
                        f"[{report_date}] chunk {chunk_id} summary {summary!r} is missing "
                        f"expected substrings {missing} — wrong chunk pinned, re-curate."
                    )
                must_have_events.append(
                    {
                        "description": description,
                        "match_any": match_any,
                        "chunk": _freeze_chunk(row),
                    }
                )
            payload = {
                "report_date": report_date,
                "description": (
                    "Curated high-impact must-have events (event_type in {M&A, 자본조달}). "
                    "These must never silently drop; the event safety net guarantees them."
                ),
                "must_have_events": must_have_events,
            }
            out_path = FIXTURE_DIR / f"{report_date}.json"
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"froze {len(must_have_events)} must-haves -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
