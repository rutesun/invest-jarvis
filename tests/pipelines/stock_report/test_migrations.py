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


def test_report_evidence_migration_preserves_evidence_snapshot_on_chunk_replacement() -> None:
    sql = Path("migrations/stock_report/007_phase1_report_evidence_snapshot.sql").read_text(
        encoding="utf-8"
    )

    assert "ADD COLUMN IF NOT EXISTS knowledge_chunk_snapshot JSONB NOT NULL DEFAULT '{}'" in sql
    assert "ALTER COLUMN knowledge_chunk_id DROP NOT NULL" in sql
    assert "DROP CONSTRAINT IF EXISTS report_evidence_knowledge_chunk_id_fkey" in sql
    assert "ADD CONSTRAINT report_evidence_knowledge_chunk_id_fkey" in sql
    assert "FOREIGN KEY (knowledge_chunk_id)" in sql
    assert "REFERENCES knowledge_chunks(id)" in sql
    assert "ON DELETE SET NULL" in sql
    assert "report_evidence_chunk_snapshot_object" in sql
