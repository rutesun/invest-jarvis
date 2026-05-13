ALTER TABLE IF EXISTS knowledge_chunks
    ADD COLUMN IF NOT EXISTS event_type TEXT;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_event_type
    ON knowledge_chunks (event_type);
