ALTER TABLE IF EXISTS knowledge_chunks
    ADD COLUMN IF NOT EXISTS evidence_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS qa_warnings JSONB NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'knowledge_chunks_evidence_items_array'
          AND conrelid = 'knowledge_chunks'::regclass
    ) THEN
        ALTER TABLE knowledge_chunks
            ADD CONSTRAINT knowledge_chunks_evidence_items_array
            CHECK (jsonb_typeof(evidence_items) = 'array');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'knowledge_chunks_qa_warnings_array'
          AND conrelid = 'knowledge_chunks'::regclass
    ) THEN
        ALTER TABLE knowledge_chunks
            ADD CONSTRAINT knowledge_chunks_qa_warnings_array
            CHECK (jsonb_typeof(qa_warnings) = 'array');
    END IF;
END $$;
