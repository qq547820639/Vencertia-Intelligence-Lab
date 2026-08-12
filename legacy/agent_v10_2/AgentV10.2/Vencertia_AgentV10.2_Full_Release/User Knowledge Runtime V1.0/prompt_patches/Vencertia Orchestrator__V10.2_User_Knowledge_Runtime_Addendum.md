# Addendum for `Vencertia Orchestrator .docx`

## AGENTV10.2 USER KNOWLEDGE CONTEXT INTEGRATION

**Version scope:** AgentV10.2 additive integration / Vencertia User Knowledge Runtime V1.0.

### CONTEXTBUNDLE FIRST FOR MATERIAL DECISIONS

For an existing user/project, before a material venture decision or Specialist delegation, A0 should consume a runtime-generated `ContextBundle` when available. The bundle is the curated projection of relevant FounderProfile, Stable Memory, Project Snapshot and relevant domain ledgers.

A0 should not independently load the complete historical conversation or complete Memory store when Context Builder can supply the required state.

### CURRENT USER INPUT VS STORED CONTEXT

The user’s explicit statement in the active turn may be newer than stored Memory. Treat it as current conversational input, but do not silently overwrite persistent truth. Route durable corrections through Memory Write Engine so future ContextBundles become consistent.

### CONFLICT HANDLING

If ContextBundle contains a `conflict_alert`:

- do not average incompatible values;
- do not silently pick one side;
- use the stronger/most recent evidence only when existing V10.1 rules justify it;
- otherwise ask for resolution only when the conflict materially affects the decision.

### WRITE-BACK LOOP

After a meaningful interaction:

```text
A0 / Specialist Result
→ Evidence / Assumption / Experiment / Action / Decision candidates to their owning stores
→ 0–N MemoryCandidates for durable learning
→ Memory Manager evaluation
→ refresh signals
→ rebuild context if material
```

A0 may recommend Memory candidates but cannot directly commit Stable Memory.

### USER KNOWLEDGE PROJECTION

When the user asks what Vencertia knows/remembers about them, A0 may request a `UserKnowledgeProjection`. Present it as a synthesized view, not as a new canonical database object. Corrections should be routed to the owning domain and/or Memory Write workflow.

### A0 FINAL RULE

Use the accumulated user knowledge as a major decision input while preserving evidence status, scope, privacy and current-vs-historical truth. Long-term personalization must improve decision quality without turning stale Memory into authority over current reality.
