ALTER TABLE telegram_messages
    ADD COLUMN IF NOT EXISTS clean_text TEXT,
    ADD COLUMN IF NOT EXISTS urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS has_media BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS content_hash TEXT,
    ADD COLUMN IF NOT EXISTS processing_mode TEXT NOT NULL DEFAULT 'full',
    ADD COLUMN IF NOT EXISTS grouped_message_ids BIGINT[] NOT NULL DEFAULT '{}';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'knowledge_chunks'
          AND column_name = 'one_line'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'knowledge_chunks'
          AND column_name = 'canonical_summary'
    ) THEN
        ALTER TABLE knowledge_chunks
            RENAME COLUMN one_line TO canonical_summary;
    END IF;
END $$;
