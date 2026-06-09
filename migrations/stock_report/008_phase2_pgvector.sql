-- Phase 2 PDF ingest: 공유 벡터 인프라.
-- pgvector >= 0.5.0 필요 (HNSW 인덱스 / vector_cosine_ops).
-- 이 파일은 확장만 켠다. document_chunks.embedding 컬럼/HNSW 인덱스는 009에서 추가한다.
-- knowledge_chunks.embedding 컬럼은 본 범위 밖(T11에서 별도 마이그레이션으로 추가).
CREATE EXTENSION IF NOT EXISTS vector;
