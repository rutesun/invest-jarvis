CREATE TABLE IF NOT EXISTS telegram_messages (
    id BIGSERIAL PRIMARY KEY,
    source_date DATE NOT NULL,
    date_kst DATE NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL,
    channel_key TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    channel_message_id TEXT NOT NULL,
    author TEXT,
    raw_text TEXT NOT NULL,
    media_info TEXT,
    forward_from_raw TEXT,
    forward_from_channel_key TEXT,
    forward_from_channel_name TEXT,
    raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_key, channel_message_id)
);

CREATE INDEX IF NOT EXISTS idx_telegram_messages_source_date
    ON telegram_messages (source_date);
CREATE INDEX IF NOT EXISTS idx_telegram_messages_date_kst
    ON telegram_messages (date_kst);
CREATE INDEX IF NOT EXISTS idx_telegram_messages_channel_key
    ON telegram_messages (channel_key);


CREATE TABLE IF NOT EXISTS forward_source_map (
    id BIGSERIAL PRIMARY KEY,
    channel_key TEXT NOT NULL,
    channel_message_id TEXT NOT NULL,
    source_channel_key TEXT,
    source_channel_name TEXT,
    source_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_key, channel_message_id)
);


CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_pk BIGINT,
    source_date DATE NOT NULL,
    channel_key TEXT,
    message_type TEXT NOT NULL,
    category_key TEXT NOT NULL,
    main_theme TEXT,
    sub_themes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ticker_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    theme_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    one_line TEXT NOT NULL,
    content_clean TEXT NOT NULL,
    embed_payload TEXT NOT NULL,
    channel_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    priority_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source
    ON knowledge_chunks (source_type, source_date);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_category_theme
    ON knowledge_chunks (category_key, main_theme);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_sub_themes
    ON knowledge_chunks USING GIN (sub_themes);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_ticker_tags
    ON knowledge_chunks USING GIN (ticker_tags);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_theme_tags
    ON knowledge_chunks USING GIN (theme_tags);


CREATE TABLE IF NOT EXISTS report_runs (
    id BIGSERIAL PRIMARY KEY,
    report_date DATE NOT NULL,
    pipeline_version TEXT NOT NULL DEFAULT 'v2',
    provider TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    output_markdown TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_runs_date
    ON report_runs (report_date);


CREATE TABLE IF NOT EXISTS report_evidence (
    id BIGSERIAL PRIMARY KEY,
    report_run_id BIGINT NOT NULL REFERENCES report_runs(id) ON DELETE CASCADE,
    section_key TEXT NOT NULL,
    item_key TEXT NOT NULL,
    knowledge_chunk_id BIGINT NOT NULL REFERENCES knowledge_chunks(id),
    rank_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_evidence_run
    ON report_evidence (report_run_id);
