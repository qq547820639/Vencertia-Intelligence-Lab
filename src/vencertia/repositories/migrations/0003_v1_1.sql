-- Vencertia v1.1 — SQLite schema (idempotent)
-- Hot-path special tables for claim bindings and belief update records.
-- All other v1.1 entity types (candidate_claim, research_plan, research_trace,
-- decision_sensitivity, decision_trace, evidence_conflict, call_record) reuse
-- the generic `entities` table from 0001_initial.sql.

CREATE TABLE IF NOT EXISTS claim_bindings (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    claim_id TEXT,
    binding_confidence REAL NOT NULL,
    binding_method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'BOUND',
    model TEXT,
    provider TEXT,
    matched_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS belief_update_records (
    id TEXT PRIMARY KEY,
    belief_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    posterior_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claim_bindings_evidence ON claim_bindings(evidence_id);
CREATE INDEX IF NOT EXISTS idx_claim_bindings_claim ON claim_bindings(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_bindings_status ON claim_bindings(status);
CREATE INDEX IF NOT EXISTS idx_bur_belief ON belief_update_records(belief_id);
