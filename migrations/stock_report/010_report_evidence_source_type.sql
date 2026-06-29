-- T17: report_evidence에 source_type 컬럼 추가 (telegram/pdf/news/disclosure 구분자).
-- DEFAULT 'telegram'으로 기존 행을 백필하고, 새 행의 기본값으로도 사용된다.
-- 기존 컬럼/제약은 변경하지 않는다 (additive only).

ALTER TABLE report_evidence
    ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'telegram';
