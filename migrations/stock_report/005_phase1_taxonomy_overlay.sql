ALTER TABLE IF EXISTS knowledge_chunks
    ADD COLUMN IF NOT EXISTS provisional_category TEXT,
    ADD COLUMN IF NOT EXISTS provisional_theme TEXT,
    ADD COLUMN IF NOT EXISTS is_provisional BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_provisional_category
    ON knowledge_chunks (provisional_category);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_is_provisional
    ON knowledge_chunks (is_provisional);
