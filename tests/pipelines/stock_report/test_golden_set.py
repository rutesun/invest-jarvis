"""Golden-set regression: frozen high-impact must-have events must never silently drop.

Hermetic by design — reads committed JSON fixtures (no DB, no LLM), so it runs in the
normal `uv run pytest` loop. Fixtures are content-based (not chunk-id based) because the
daily-v2 pipeline re-ingests chunks with fresh ids on every run.

Regenerate fixtures with: uv run python scripts/stock_report_freeze_golden.py

Each must-have is validated two ways:
1. its frozen event_type is a high-impact type the safety net protects (precondition);
2. when the LLM drops it (uncited), the safety net actually re-surfaces it on the real
   event shape (the mechanism, exercised on production data — not synthetic chunks).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.pipelines.stock_report.event_safety_net import (
    HIGH_IMPACT_EVENT_TYPES,
    enforce_high_impact_event_coverage,
)
from src.pipelines.stock_report.retrieval import SameDayChunk
from src.pipelines.stock_report.synthesize import CategorySummaryCard


GOLDEN_DIR = Path(__file__).parents[2] / "fixtures" / "stock_report" / "golden"
EXPECTED_DATES = {"2026-05-28", "2026-06-02"}


def _load_cases() -> list[Any]:
    cases: list[Any] = []
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for index, event in enumerate(data["must_have_events"]):
            cases.append(pytest.param(event, id=f"{data['report_date']}-{index}"))
    return cases


ALL_MUST_HAVES = _load_cases()


def _chunk_from_frozen(chunk_id: int, frozen: dict[str, Any]) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 1, 1),
        channel_key="golden",
        channel_name="golden",
        channel_message_id=str(chunk_id),
        message_type="signal",
        event_type=frozen["event_type"],
        category_key=frozen["category_key"],
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=[],
        theme_tags=[],
        canonical_summary=frozen["canonical_summary"],
        supporting_facts=list(frozen["supporting_facts"]),
        evidence_items=[],
        qa_warnings=[],
        content_clean="",
        priority_score=float(frozen["priority_score"]),
    )


def test_golden_fixtures_present() -> None:
    found_dates = {path.stem for path in GOLDEN_DIR.glob("*.json")}
    assert found_dates >= EXPECTED_DATES, f"missing golden fixtures: {EXPECTED_DATES - found_dates}"
    assert ALL_MUST_HAVES, "no golden must-have events loaded"


@pytest.mark.parametrize("event", ALL_MUST_HAVES)
def test_must_have_event_type_is_protected(event: dict[str, Any]) -> None:
    event_type = event["chunk"]["event_type"]
    assert event_type in HIGH_IMPACT_EVENT_TYPES, (
        f"must-have '{event['description']}' has event_type={event_type!r} which the safety "
        f"net no longer protects — it could silently drop again."
    )


@pytest.mark.parametrize("event", ALL_MUST_HAVES)
def test_safety_net_resurfaces_dropped_must_have(event: dict[str, Any]) -> None:
    chunk = _chunk_from_frozen(999_001, event["chunk"])
    # Simulate the LLM consolidating the category but dropping this event (id not cited).
    card = CategorySummaryCard(
        category_key=chunk.category_key,
        title=chunk.category_key,
        narrative="LLM 종합 서사 (이 이벤트는 누락)",
        evidence_bullets=[],
        impact="",
        related_stocks=[],
        evidence_chunk_ids=[],
        priority_score=1.0,
    )

    result = enforce_high_impact_event_coverage(card, [chunk])

    assert 999_001 in result.evidence_chunk_ids, (
        f"safety net failed to re-surface dropped must-have '{event['description']}'"
    )
    assert any(chunk.canonical_summary in bullet for bullet in result.evidence_bullets), (
        f"must-have '{event['description']}' summary not present in any evidence bullet"
    )
