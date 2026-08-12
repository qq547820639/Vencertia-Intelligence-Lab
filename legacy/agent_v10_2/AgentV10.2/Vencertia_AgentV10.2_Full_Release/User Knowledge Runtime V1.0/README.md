# Vencertia User Knowledge Runtime V1.0

Compatibility target: **AgentV10.1**.
Release intent: add a production-oriented user knowledge runtime **without modifying or replacing any AgentV10.1 canonical prompt body, MemoryRecord contract, Project KB, Evidence, Assumption, Experiment, Action, Decision, Financial Snapshot, or Company Intelligence schema**.

## Core architectural rule

`User Knowledge` is a **composite read/orchestration layer**, not a new canonical fact entity.

Canonical ownership remains:

- `FounderProfile` — current structured Founder state.
- `MemoryRecord` — curated durable user/project memory.
- `Project KB / ProjectSnapshot` — project state/history.
- Evidence / Assumption / Experiment / Action / Decision / Financial Snapshot — their own ledgers/stores.
- Company Intelligence Runtime V1.1 — external company-case intelligence.

This runtime deliberately does **not** define `KnowledgeRecord`, `KnowledgeType`, or a `knowledge_records` table.

## Runtime flow

```text
User / Agent / Tool Event
        ↓
MemoryCandidate extraction
        ↓
MemoryCandidateEnvelope (runtime metadata only)
        ↓
Memory Manager
  proper-store / authority / duplicate / temporal / conflict checks
        ↓
WRITE / MERGE / SUPERSEDE / CONFLICT / REJECT / EXPIRE / ARCHIVE
        ↓
MemoryRecord canonical persistence
        ↓
Profile/Snapshot/Context refresh signals
        ↓
Context Builder
        ↓
ContextBundle (task-specific projection)
        ↓
A0 / A1 ... A10
```

## Files

- `runtime/models.py` — AgentV10.1-aligned Pydantic V2 contracts.
- `runtime/memory_manager.py` — write/merge/supersede/conflict runtime.
- `runtime/memory_repository.py` — repository protocol + deterministic in-memory implementation.
- `runtime/memory_write_policy.py` — proper-store and write-authority rules.
- `runtime/memory_retrieval_policy.py` — tenant/project/privacy/status/ranking retrieval.
- `runtime/memory_conflict_resolver.py` — conservative semantic adjudication boundary.
- `runtime/memory_deduplicator.py` — exact deterministic duplicate logic.
- `runtime/memory_permissions.py` — PRIVATE/MATCHABLE/PUBLIC access projection.
- `runtime/context_builder.py` — A0–A10 task-specific ContextBundle assembly.
- `runtime/founder_profile_sync.py` — refresh request generation; does not create a second FounderProfile store.
- `runtime/user_knowledge_service.py` — façade for user-facing knowledge projection + Agent context.
- `schema.sql` — PostgreSQL canonical Memory persistence and runtime metadata tables.
- `generate_json_schema.py` + `json_schema/` — generated runtime DTO contracts.
- `prompt_patches/` — V10.2 additive appendices; originals remain untouched.
- `compatibility_audit.json` — original hashes + zero-conflict assertions.

## Run

```bash
python generate_json_schema.py
pytest -q
python zero_conflict_audit.py
```

## Important non-goals

This package does not implement the full Founder/Profile/Project/Evidence databases because AgentV10.1 already defines those as separate domains. `ContextDataProvider` is the integration boundary for those canonical stores.

The in-memory repository exists for deterministic tests and integration development. Production should use PostgreSQL according to `schema.sql` and enforce tenant ownership at the application/database layer.
