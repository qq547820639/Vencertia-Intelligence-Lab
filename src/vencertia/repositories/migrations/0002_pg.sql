-- Vencertia v1.0 — PostgreSQL schema (type-adapted, idempotent)

CREATE TABLE IF NOT EXISTS entities (
    entity_type TEXT NOT NULL,
    id TEXT NOT NULL,
    payload JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (entity_type, id)
);

CREATE TABLE IF NOT EXISTS event_log (
    seq BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL DEFAULT 'system',
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
