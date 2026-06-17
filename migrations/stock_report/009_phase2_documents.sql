-- Phase 2 PDF ingest: documents + document_chunks (small-to-big) + report_evidence 링크.
-- 008(CREATE EXTENSION vector)이 먼저 적용되므로 vector 타입/hnsw 접근 메서드가 준비돼 있다.
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    content_hash TEXT,
    broker_key TEXT,
    broker_name TEXT,
    title TEXT,
    published_date DATE,
    target_ticker TEXT,
    category_key TEXT,
    main_theme TEXT,
    page_count INTEGER,
    parse_mode TEXT NOT NULL DEFAULT 'local',       -- local | hybrid
    parser_version TEXT,                             -- 파서 버전 (재파스 정책, Codex #3)
    parse_status TEXT NOT NULL DEFAULT 'ok',         -- ok | low_confidence | needs_ocr | failed (Codex #5)
    needs_hybrid BOOLEAN NOT NULL DEFAULT FALSE,     -- 융합 표 감지 시 hybrid 재처리 대상 (2패스에서 소비)
    text_char_count INTEGER,
    markdown TEXT,                                   -- 전문 보관 → 재청킹 시 재파싱 불필요
    parse_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_published_date ON documents (published_date);
CREATE INDEX IF NOT EXISTS idx_documents_target_ticker ON documents (target_ticker);
CREATE INDEX IF NOT EXISTS idx_documents_parse_status ON documents (parse_status);
CREATE INDEX IF NOT EXISTS idx_documents_needs_hybrid ON documents (needs_hybrid);

CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,  -- A1 해소: 정식 FK + cascade
    source_date DATE NOT NULL,
    broker_key TEXT,
    section_path TEXT NOT NULL,        -- small-to-big 부모 키
    chunk_seq INTEGER NOT NULL,        -- 문서 내 순서 (부모 복원/이웃 윈도우용)
    is_table BOOLEAN NOT NULL DEFAULT FALSE,
    category_key TEXT,
    main_theme TEXT,
    ticker_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    canonical_summary TEXT NOT NULL,
    content_clean TEXT NOT NULL,
    embed_payload TEXT NOT NULL,
    embedding vector(1536),                        -- 비동기로 채움(처음 NULL, Codex #4)
    embed_model TEXT,
    embed_version TEXT,
    embed_status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | failed
    embed_attempts INTEGER NOT NULL DEFAULT 0,
    priority_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, section_path, chunk_seq)
);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_ticker ON document_chunks USING GIN (ticker_tags);
CREATE INDEX IF NOT EXISTS idx_document_chunks_section ON document_chunks (document_id, section_path, chunk_seq);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embed_status ON document_chunks (embed_status);  -- 패스2 pending 조회

-- PDF evidence도 추적 가능하게 (knowledge_chunk_id와 둘 중 하나).
-- additive/nullable → Phase 1 report_evidence 저장 경로 회귀 없음.
ALTER TABLE IF EXISTS report_evidence
    ADD COLUMN IF NOT EXISTS document_chunk_id BIGINT REFERENCES document_chunks(id) ON DELETE SET NULL;
