-- T18: PDF 검색 쿼리 로그 테이블.
-- synthesis 단계에서 search_documents 도구로 실행한 쿼리·결과를 기록한다.
-- 검색 커버리지 분석·프롬프트 개선 시 참조용.

CREATE TABLE IF NOT EXISTS pdf_search_log (
    id            BIGSERIAL PRIMARY KEY,
    report_run_id BIGINT  NOT NULL REFERENCES report_runs(id) ON DELETE CASCADE,
    label         TEXT    NOT NULL,
    label_type    TEXT    NOT NULL,
    query         TEXT    NOT NULL,
    category      TEXT,
    ticker        TEXT,
    top_k         INT     NOT NULL DEFAULT 3,
    hit_count     INT     NOT NULL DEFAULT 0,
    hit_chunk_ids JSONB   NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pdf_search_log_report_run
    ON pdf_search_log (report_run_id);

CREATE INDEX IF NOT EXISTS idx_pdf_search_log_label
    ON pdf_search_log (label, label_type);
