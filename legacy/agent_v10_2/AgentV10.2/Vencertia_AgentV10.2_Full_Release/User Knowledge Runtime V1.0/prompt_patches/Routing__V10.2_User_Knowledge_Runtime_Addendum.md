# Addendum for `Routing.docx`

## AGENTV10.2 USER KNOWLEDGE CONTEXT ROUTING

**Version scope:** AgentV10.2 additive integration / Vencertia User Knowledge Runtime V1.0.

### USER_KNOWLEDGE_CONTEXT IS A RETRIEVAL CLASS, NOT A STORE

Router may request a logical context class named `USER_KNOWLEDGE_CONTEXT`. It means:

> Build the minimum relevant ContextBundle from FounderProfile, Stable Memory, Project KB and relevant domain ledgers.

It does **not** mean query a new generic KnowledgeRecord database.

### ROUTER OUTPUT

For material Agent calls, Routing may specify:

- required_context_classes
- active user_id
- active project_id if applicable
- target Agent
- current task/intent
- input_state_version

The Context Builder retrieves actual records. Router must not SELECT or serialize the full User Memory/Project KB itself.

### CONTEXT REBUILD TRIGGERS

Invalidate/rebuild ContextBundle after material changes such as:

- explicit user correction of a durable Founder constraint/resource/red line
- accepted Memory SUPERSEDE or CONFLICT
- real payment or major Evidence arrival
- formal Project Decision
- material Financial Snapshot change
- stage/bottleneck/state mutation

Do not continue a precomputed multi-Agent plan with stale context.

### AGENT-SPECIFIC LEAST PRIVILEGE

Preserve existing Router least-privilege rules. In particular:

- A8: receive only minimum project query context; do not export raw private Memory to external tools.
- A9: receive only permissioned MATCHABLE/PUBLIC user signals for exposure.
- A5: retrieve current Financial Snapshot separately from durable Memory.
- A0: broad internal context is allowed, but still token-curated.

### MEMORY WRITE AUTHORITY

Routing may create/forward a Memory Write request containing `MemoryCandidateEnvelope[]`. It cannot commit Stable Memory. Memory Manager remains the mutation owner.

### ROUTING PRINCIPLE

The Router decides **what context classes are required**. Context Builder decides **which records fit those classes**. This preserves tenant isolation, project isolation, privacy and token discipline.
