from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from src.pipelines.stock_report.db import persist_classified_chunks
from src.pipelines.stock_report.models import (
    ClassifiedMessage,
    EvidenceItem,
    NormalizedMessage,
    QAWarning,
)


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.conn.executed.append((query, params))

    def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        self.conn.executemany_calls.append((query, params))


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


def _normalized() -> NormalizedMessage:
    return NormalizedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        channel_key="hana_us_stock",
        source_channel_key="hana_us_stock",
        source_channel_name="하나증권",
        channel_message_id="1",
        raw_text="Seagate 주가 8% 하락",
        clean_text="Seagate 주가 8% 하락",
        urls=[],
        has_media=False,
        content_hash="hash",
        processing_mode="full",
        grouped_message_ids=[],
    )


def test_persist_classified_chunks_serializes_typed_evidence_and_warnings() -> None:
    conn = FakeConnection()
    normalized = _normalized()
    classified = ClassifiedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        channel_key="hana_us_stock",
        source_channel_key="hana_us_stock",
        processing_mode="full",
        structure_type="single_topic_deep",
        unit_index=0,
        message_type="signal",
        event_type="해석/전망",
        category_key="반도체",
        main_theme=None,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=["Seagate"],
        canonical_summary="Seagate 주가 하락",
        supporting_facts=["Seagate 주가는 8% 하락"],
        evidence_items=[EvidenceItem(kind="metric", text="Seagate 주가는 8% 하락")],
        qa_warnings=[QAWarning(code="missing_metric_candidate", detail="test")],
    )

    persist_classified_chunks(
        conn,
        normalized_messages=[normalized],
        classified_messages=[classified],
    )

    assert len(conn.executemany_calls) == 1
    query, params = conn.executemany_calls[0]
    assert "evidence_items" in query
    assert "qa_warnings" in query
    payload = params[0]
    assert json.loads(payload[15]) == ["Seagate 주가는 8% 하락"]
    assert json.loads(payload[16]) == [{"kind": "metric", "text": "Seagate 주가는 8% 하락"}]
    assert json.loads(payload[17]) == [{"code": "missing_metric_candidate", "detail": "test"}]
    assert conn.commits == 1
