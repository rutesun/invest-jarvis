from __future__ import annotations

from pathlib import Path


def test_typed_evidence_migration_adds_jsonb_columns_and_array_constraints() -> None:
    sql = Path("migrations/stock_report/006_phase1_typed_evidence.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS evidence_items JSONB NOT NULL DEFAULT '[]'::jsonb" in sql
    assert "ADD COLUMN IF NOT EXISTS qa_warnings JSONB NOT NULL DEFAULT '[]'::jsonb" in sql
    assert "knowledge_chunks_evidence_items_array" in sql
    assert "knowledge_chunks_qa_warnings_array" in sql
    assert "conrelid = 'knowledge_chunks'::regclass" in sql
    assert "jsonb_typeof(evidence_items) = 'array'" in sql
    assert "jsonb_typeof(qa_warnings) = 'array'" in sql
