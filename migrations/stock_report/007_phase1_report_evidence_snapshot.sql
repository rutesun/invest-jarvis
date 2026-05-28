ALTER TABLE IF EXISTS report_evidence
    ADD COLUMN IF NOT EXISTS knowledge_chunk_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS report_evidence
    ALTER COLUMN knowledge_chunk_id DROP NOT NULL;

ALTER TABLE IF EXISTS report_evidence
    DROP CONSTRAINT IF EXISTS report_evidence_knowledge_chunk_id_fkey;

ALTER TABLE IF EXISTS report_evidence
    ADD CONSTRAINT report_evidence_knowledge_chunk_id_fkey
    FOREIGN KEY (knowledge_chunk_id)
    REFERENCES knowledge_chunks(id)
    ON DELETE SET NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'report_evidence_chunk_snapshot_object'
          AND conrelid = 'report_evidence'::regclass
    ) THEN
        ALTER TABLE report_evidence
            ADD CONSTRAINT report_evidence_chunk_snapshot_object
            CHECK (jsonb_typeof(knowledge_chunk_snapshot) = 'object');
    END IF;
END $$;
