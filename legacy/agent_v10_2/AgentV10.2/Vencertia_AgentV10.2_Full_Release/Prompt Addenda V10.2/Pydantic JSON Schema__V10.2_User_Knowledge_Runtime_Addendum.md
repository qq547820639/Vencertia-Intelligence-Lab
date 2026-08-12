# Addendum for `Pydantic  JSON Schema.docx`

## AGENTV10.2 USER KNOWLEDGE RUNTIME SCHEMA INTEGRATION

**Version scope:** AgentV10.2 additive integration / Vencertia User Knowledge Runtime V1.0.

### V10.2 PRECEDENCE

This appendix is authoritative only for User Knowledge Runtime DTOs and the Monetization Distance consistency correction below. Existing AgentV10.1 domain boundaries remain unchanged.

### NO GENERIC CANONICAL KNOWLEDGE ENTITY

Do not introduce a new canonical:

- KnowledgeRecord
- KnowledgeType
- KnowledgeStatus
- knowledge_records persistence table

`MemoryRecord` remains the canonical durable personalized knowledge object. FounderProfile, Project KB, Evidence, Assumption, Experiment, Action, Decision, Financial Snapshot and Startup Intelligence remain separate domain models.

### PRESERVE CANONICAL MEMORY ENUMS

V10.2 User Knowledge Runtime must reuse the existing AgentV10.1 values exactly.

MemoryScope:
`USER_GLOBAL | PROJECT_SPECIFIC`

MemoryStatus:
`ACTIVE | SUPERSEDED | CONFLICTED | REJECTED | EXPIRED | ARCHIVED`

MemoryType:
`FOUNDER_FACT | RESOURCE | CAPABILITY | CONSTRAINT | RED_LINE | PREFERENCE | PROJECT_FACT | PROJECT_DECISION | ASSUMPTION | EVIDENCE | CUSTOMER_FEEDBACK | EXPERIMENT_RESULT | FINANCIAL_DATA | RISK | ACTION | ACTION_RESULT | MILESTONE | OPEN_QUESTION | EXCLUSION_RULE | PIVOT_REASON | LESSON`

Memory SourceType values for this runtime:
`USER_EXPLICIT_INPUT | USER_CORRECTION | CUSTOMER_FEEDBACK | EXPERIMENT_RESULT | REAL_PAYMENT | PROJECT_DECISION | AGENT_INFERENCE | DOCUMENT_CLAIM | WEB_SOURCE | SYSTEM_DERIVED | TOOL_RESULT`

Do not create synonymous enum families for this release.

### NEW RUNTIME DTO — MemoryCandidateEnvelope

Add a runtime-only wrapper around canonical `MemoryCandidate` for deterministic integration metadata:

```text
MemoryCandidateEnvelope
- candidate: MemoryCandidate
- source_types[]
- evidence_ids[]
- semantic_key?
- proper_store
- access_class
- origin_agent?
```

This is not persisted as a new knowledge fact entity.

### NEW RUNTIME DTO — ContextBuildRequest

Conceptual fields:

```text
request_id
user_id
project_id?
agent_id
task
max_memory_records
token_budget
as_of?
```

### ContextBundle V10.2 PROJECTION

Continue using `ContextBundle` as the token-efficient Agent input DTO. It may include:

```text
founder_profile
project_snapshot
founder_stable_memory
current_stage
current_bottleneck
critical_assumptions
top_evidence
latest_experiments
latest_decisions
relevant_memories
exclusion_rules
conflict_alerts
recent_messages
retrieval_notes
```

This bundle is a read projection. It must not become a persistence model or new source of truth.

### NEW READ DTO — UserKnowledgeProjection

A user-facing Knowledge Base view may be represented by a read-only DTO containing:

```text
user_id
project_id?
founder_profile
global_memories
project_memories
unresolved_conflicts
project_summaries
generated_at
```

It must explicitly document that canonical data remains in FounderProfile, MemoryRecord, Project KB and the domain ledgers.

### MEMORY PERMISSION METADATA

Runtime/persistence may attach an access class to a MemoryRecord without changing the semantic MemoryRecord contract:

`PRIVATE | INTERNAL | MATCHABLE | PUBLIC`

Default is PRIVATE. A9 exposure uses MATCHABLE/PUBLIC only.

### DOMAIN MODEL VS DTO

Keep the existing AgentV10.1 rule:

- Domain Model = canonical business entity.
- Agent Input DTO = task context.
- Agent Output DTO = recommendation/candidate.
- Persistence metadata = database/runtime enforcement.

User Knowledge Runtime relies on this distinction.

### V10.2 MONETIZATION DISTANCE CONSISTENCY CORRECTION

AgentV10.1 section 43 lists four meanings:

1. direct close
2. direct prospect reach
3. effective referral
4. generic relation

Therefore the canonical valid range for `monetization_distance` is **1, 2, 3, 4**. Reject values outside 1–4. This correction changes no documented meaning; it resolves the 1–3/1–4 inconsistency.

### JSON SCHEMA GENERATION

Generate JSON Schema from Pydantic V2 models for the new runtime DTOs. Do not hand-maintain divergent schema copies.
