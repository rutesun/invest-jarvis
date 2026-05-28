ALTER TABLE IF EXISTS knowledge_chunks
    ADD COLUMN IF NOT EXISTS supporting_facts JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_supporting_facts
    ON knowledge_chunks USING GIN (supporting_facts);
