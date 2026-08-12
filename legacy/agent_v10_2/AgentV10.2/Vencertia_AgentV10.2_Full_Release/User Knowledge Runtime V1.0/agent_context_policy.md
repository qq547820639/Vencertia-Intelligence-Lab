# Agent Context Policy — Vencertia User Knowledge Runtime V1.0

## Non-negotiable

A0–A10 do not receive the full conversation history or the full Memory store. The Router requests context classes; the Context Builder retrieves actual records and emits a token-efficient `ContextBundle`.

## Canonical precedence

1. Current explicit user input in the active turn (not yet durable until written).
2. Current evidence-backed / VERIFIED project reality.
3. Current `ACTIVE` durable Memory.
4. ESTIMATED durable Memory, clearly labeled.
5. ASSUMED/UNKNOWN durable Memory, clearly labeled.
6. Historical SUPERSEDED/ARCHIVED Memory only when the task needs history.
7. CONFLICTED Memory is surfaced as conflict, never silently averaged.

## Agent defaults

| Agent | Memory focus | Extra rule |
|---|---|---|
| A0 | broad Founder + project durable Memory | receives curated ContextBundle before material project decisions |
| A1 | Founder facts/capabilities/resources/constraints/preferences/red lines | may emit MemoryCandidates; cannot commit |
| A2 | capability/resource/constraint/preference/red line/lesson/exclusion | use history to avoid repeated poor opportunity spaces |
| A3 | A2 context + project decisions/pivot reasons | previous rejection/kill knowledge must constrain new design |
| A4 | risk/lessons/exclusions/pivots + Founder constraints | retrieve negative history aggressively |
| A5 | constraints + durable financial memory + decisions/risks | latest Financial Snapshot is authoritative for current metrics |
| A6 | capability/resource/constraints + decisions/action results | execution strategy itself is not Stable Memory |
| A7 | current constraints/resources + action/experiment lessons | recent state dominates; do not repeat completed failed actions |
| A8 | minimal project facts/risks/lessons | raw private Memory must not be exported to external research tools |
| A9 | MATCHABLE/PUBLIC founder signals only | never receives full private Memory for exposure |
| A10 | project facts/decisions/financial/risk/evidence/assumption labels | BP must not upgrade assumptions to facts |

## Cross-project learning

Project-specific records stay project-specific. Promotion to USER_GLOBAL must be deliberate and normally represented as a durable `LESSON`, `EXCLUSION_RULE`, `CAPABILITY`, `RESOURCE`, `CONSTRAINT`, `PREFERENCE`, `RED_LINE`, or other already-approved MemoryType. No new GOAL/FOUNDER_FIT/ANTI_PATTERN top-level Memory enums are introduced by this runtime.

## Privacy

Memory is PRIVATE by default. `access_class` is runtime/persistence permission metadata and does not change the canonical `MemoryRecord` semantic contract. A9 uses MATCHABLE/PUBLIC only. A8 receives only minimal internal context and must create a privacy-safe external query payload.
