-- Vencertia v1.1 — PostgreSQL schema (idempotent, PG dialect)
-- Hot-path special tables for claim bindings and belief update records.
-- Mirrors 0003_v1_1.sql (SQLite) but uses PostgreSQL types (JSONB/TIMESTAMPTZ).

CREATE TABLE IF NOT EXISTS claim_bindings (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    claim_id TEXT,
    binding_confidence DOUBLE PRECISION NOT NULL,
    binding_method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'BOUND',
    model TEXT,
    provider TEXT,
    matched_at TIMESTAMPTZ NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS belief_update_records (
    id TEXT PRIMARY KEY,
    belief_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    posterior_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claim_bindings_evidence ON claim_bindings(evidence_id);
CREATE INDEX IF NOT EXISTS idx_claim_bindings_claim ON claim_bindings(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_bindings_status ON claim_bindings(status);
CREATE INDEX IF NOT EXISTS idx_bur_belief ON belief_update_records(belief_id);
