-- Vencertia User Knowledge Runtime V1.0
-- Compatible with AgentV10.1. PostgreSQL is the canonical structured Memory store.
-- This schema intentionally contains NO knowledge_records table.
-- FounderProfile / Project KB / Evidence / Assumption / Experiment / Action / Decision /
-- Financial Snapshot remain separate AgentV10.1 domain stores.

CREATE TABLE IF NOT EXISTS memory_records (
    memory_id                  text PRIMARY KEY,
    user_id                    text NOT NULL,
    project_id                 text NULL,
    scope                      text NOT NULL CHECK (scope IN ('USER_GLOBAL','PROJECT_SPECIFIC')),
    memory_type                text NOT NULL CHECK (memory_type IN (
        'FOUNDER_FACT','RESOURCE','CAPABILITY','CONSTRAINT','RED_LINE','PREFERENCE',
        'PROJECT_FACT','PROJECT_DECISION','ASSUMPTION','EVIDENCE','CUSTOMER_FEEDBACK',
        'EXPERIMENT_RESULT','FINANCIAL_DATA','RISK','ACTION','ACTION_RESULT','MILESTONE',
        'OPEN_QUESTION','EXCLUSION_RULE','PIVOT_REASON','LESSON'
    )),
    content                    text NOT NULL,
    structured_value           jsonb NULL,
    source_message_ids         jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_entity_ids          jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_ids               jsonb NOT NULL DEFAULT '[]'::jsonb,
    fact_status                text NOT NULL CHECK (fact_status IN ('VERIFIED','ESTIMATED','ASSUMED','UNKNOWN')),
    confidence                 text NOT NULL CHECK (confidence IN ('LOW','MEDIUM','HIGH')),
    importance                 text NOT NULL CHECK (importance IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    status                     text NOT NULL CHECK (status IN ('ACTIVE','SUPERSEDED','CONFLICTED','REJECTED','EXPIRED','ARCHIVED')),
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz NOT NULL DEFAULT now(),
    valid_from                 timestamptz NULL,
    valid_to                   timestamptz NULL,
    supersedes_memory_id       text NULL REFERENCES memory_records(memory_id),
    conflicts_with_memory_ids  jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Runtime/persistence metadata. These do not create a new canonical LLM entity.
    semantic_key               text NULL,
    source_types               jsonb NOT NULL DEFAULT '[]'::jsonb,
    access_class               text NOT NULL DEFAULT 'PRIVATE' CHECK (access_class IN ('PRIVATE','INTERNAL','MATCHABLE','PUBLIC')),
    row_version                bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),

    CONSTRAINT memory_scope_project_ck CHECK (
        (scope='PROJECT_SPECIFIC' AND project_id IS NOT NULL)
        OR (scope='USER_GLOBAL' AND project_id IS NULL)
    ),
    CONSTRAINT memory_validity_ck CHECK (
        valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from
    )
);

CREATE INDEX IF NOT EXISTS idx_memory_user_status
    ON memory_records (user_id, status, importance, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_project_status
    ON memory_records (user_id, project_id, status, importance, updated_at DESC)
    WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_semantic_family
    ON memory_records (user_id, project_id, memory_type, semantic_key, status)
    WHERE semantic_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS memory_conflicts (
    conflict_id                text PRIMARY KEY,
    user_id                    text NOT NULL,
    project_id                 text NULL,
    semantic_key               text NULL,
    memory_ids                 jsonb NOT NULL,
    reason                     text NOT NULL,
    resolved                   boolean NOT NULL DEFAULT false,
    resolution_note            text NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    resolved_at                timestamptz NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_conflicts_open
    ON memory_conflicts (user_id, project_id, resolved);

CREATE TABLE IF NOT EXISTS memory_write_audit (
    audit_id                   bigserial PRIMARY KEY,
    request_id                 text NOT NULL,
    candidate_id               text NOT NULL,
    user_id                    text NOT NULL,
    project_id                 text NULL,
    idempotency_key            text NOT NULL,
    actor_id                   text NOT NULL,
    operation                  text NOT NULL CHECK (operation IN ('WRITE','MERGE','SUPERSEDE','CONFLICT','REJECT','EXPIRE','ARCHIVE')),
    target_memory_id           text NULL,
    candidate_envelope         jsonb NOT NULL,
    result_payload             jsonb NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key, candidate_id)
);

CREATE TABLE IF NOT EXISTS memory_search_index (
    memory_id                  text PRIMARY KEY REFERENCES memory_records(memory_id) ON DELETE CASCADE,
    user_id                    text NOT NULL,
    embedding_provider         text NOT NULL,
    embedding_model            text NOT NULL,
    embedding_version          text NOT NULL,
    indexed_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS context_build_audit (
    context_bundle_id          text PRIMARY KEY,
    request_id                 text NOT NULL,
    user_id                    text NOT NULL,
    project_id                 text NULL,
    agent_id                   text NOT NULL,
    selected_memory_ids        jsonb NOT NULL DEFAULT '[]'::jsonb,
    generated_at               timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW active_memory AS
SELECT *
FROM memory_records
WHERE status='ACTIVE'
  AND (valid_from IS NULL OR valid_from <= now())
  AND (valid_to IS NULL OR valid_to >= now());

CREATE OR REPLACE VIEW matchable_memory AS
SELECT memory_id, user_id, project_id, scope, memory_type, content, fact_status, confidence, importance
FROM active_memory
WHERE access_class IN ('MATCHABLE','PUBLIC');
