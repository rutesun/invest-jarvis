from __future__ import annotations

from pathlib import Path


MIGRATIONS_DIR = Path("migrations/stock_report")


def _read_migration(filename: str) -> str:
    return (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")


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


def test_pgvector_migration_enables_vector_extension() -> None:
    sql = _read_migration("008_phase2_pgvector.sql")

    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql


def test_documents_migration_creates_documents_table_with_hybrid_routing() -> None:
    sql = _read_migration("009_phase2_documents.sql")

    assert "CREATE TABLE IF NOT EXISTS documents" in sql
    assert "id BIGSERIAL PRIMARY KEY" in sql
    assert "source_path TEXT NOT NULL UNIQUE" in sql
    assert "parser_version TEXT" in sql
    assert "parse_status TEXT NOT NULL DEFAULT 'ok'" in sql
    assert "needs_hybrid BOOLEAN NOT NULL DEFAULT FALSE" in sql
    assert "parse_warnings JSONB NOT NULL DEFAULT '[]'::jsonb" in sql
    assert (
        "CREATE INDEX IF NOT EXISTS idx_documents_needs_hybrid ON documents (needs_hybrid)" in sql
    )


def test_documents_migration_creates_document_chunks_table_with_vector_index() -> None:
    sql = _read_migration("009_phase2_documents.sql")

    assert "CREATE TABLE IF NOT EXISTS document_chunks" in sql
    assert "document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE" in sql
    assert "section_path TEXT NOT NULL" in sql
    assert "embedding vector(1536)" in sql
    assert "embed_status TEXT NOT NULL DEFAULT 'pending'" in sql
    assert "UNIQUE (document_id, section_path, chunk_seq)" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "USING GIN (ticker_tags)" in sql


def test_documents_migration_links_report_evidence_additively() -> None:
    """report_evidence ALTER가 additive/nullable인지 — Phase 1 저장 경로 회귀 방지."""
    sql = _read_migration("009_phase2_documents.sql")

    assert "ALTER TABLE IF EXISTS report_evidence" in sql
    assert "ADD COLUMN IF NOT EXISTS document_chunk_id BIGINT" in sql
    assert "REFERENCES document_chunks(id) ON DELETE SET NULL" in sql

    # 회귀 가드: report_evidence ALTER 블록은 추가 전용 — nullable 컬럼 1개만 더하고,
    # 기존 컬럼/제약을 DROP하거나 새 NOT NULL을 강제하지 않는다(Phase 1 저장 안 깨짐).
    alter_block = sql.split("ALTER TABLE IF EXISTS report_evidence", 1)[1]
    assert "DROP" not in alter_block
    assert "NOT NULL" not in alter_block.replace("ADD COLUMN IF NOT EXISTS", "")


def test_source_type_migration_adds_column_and_backfills_telegram() -> None:
    """010 마이그레이션이 source_type 컬럼을 추가하고 기존 행을 'telegram'으로 백필한다."""
    sql = _read_migration("010_report_evidence_source_type.sql")

    assert "ALTER TABLE" in sql
    assert "report_evidence" in sql
    assert "ADD COLUMN IF NOT EXISTS source_type TEXT" in sql
    # 기존 행 telegram 백필: DEFAULT 'telegram' 또는 UPDATE SET source_type = 'telegram'
    assert "'telegram'" in sql
    # 가드: 기존 컬럼 DROP 금지
    assert "DROP COLUMN" not in sql
