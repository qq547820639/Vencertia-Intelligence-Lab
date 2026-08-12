# Vencertia AgentV10.2 — Full Release Upgrade Manifest

## Release identity

- Package version: **AgentV10.2**
- Base release: AgentV10.1 Full Release
- Upgrade style: **additive / zero-loss**
- New subsystem: **Vencertia User Knowledge Runtime V1.0**

## Preservation rule

AgentV10.2 inherits every AgentV10.1 release file. The exact original `AgentV10.1.zip` is also embedded under `V10.1_Original_Source/` for byte-for-byte archival comparison.

## Prompt changes

Exactly five Prompt documents are upgraded by appending a V10.2 appendix after the original V10.1 body:

1. `Memory Write.docx`
2. `Pydantic  JSON Schema.docx`
3. `Routing.docx`
4. `Vencertia Orchestrator .docx`
5. `Vencertia Financial & Business Model.docx`

The original V10.1 text is not deleted. The remaining 10 Prompt DOCX files are copied unchanged.

Standalone markdown addenda and the combined patch DOCX are retained under `Prompt Addenda V10.2/`.

## User Knowledge Runtime V1.0

Added under `User Knowledge Runtime V1.0/`:

- V10.1-aligned Memory runtime models and JSON Schemas
- Memory Manager / write policy / conflict resolver / deduplicator
- permission metadata and retrieval policy
- Context Builder and UserKnowledgeProjection
- FounderProfile refresh signaling
- PostgreSQL schema
- tests and examples
- zero-conflict compatibility audit

## Canonical boundaries retained

- `MemoryRecord` remains the canonical durable personalized knowledge object.
- `FounderProfile` remains the canonical Founder profile object.
- Project KB, Evidence, Assumption, Experiment, Action, Decision and Financial Snapshot remain separate canonical domains.
- No generic canonical `KnowledgeRecord` or `knowledge_records` table is introduced.
- Company Intelligence Runtime V1.1 and its JSON Schemas remain unchanged.
- Database template V3 / Company Case Schema remains unchanged.

## V10.2 consistency correction

The Pydantic / JSON Schema appendix resolves the Monetization Distance range inconsistency by defining valid values as **1, 2, 3, 4**, matching the four meanings already documented in V10.1.

## Runtime behavior

Before important Agent calls, Context Builder may assemble a task-specific ContextBundle from authorized FounderProfile, Memory, Project KB and relevant ledgers. User Knowledge unifies access; it does not replace canonical truth ownership.
