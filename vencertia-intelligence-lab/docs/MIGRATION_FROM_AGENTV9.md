# Migration from AgentV9 prompt system

## Keep as principles

The existing materials contain several strong invariants that survive the rewrite: reality/payment over interest, evidence labels, project truth separated from conversation, stage must be earned, rollback/pivot/kill are valid, opportunity cost matters, and specialists must not mutate canonical state directly.

## Replace

| AgentV9 construct | v0.1 replacement |
|---|---|
| Orchestrator | Decision Runtime + deterministic state policy |
| Routing agent | Task/Tool Router adapter; not a business authority |
| Market Opportunity | Research/Opportunity inference module feeding Evidence |
| Venture Design | Candidate option generator |
| Project Prosecutor | Counter-hypothesis / falsification module |
| Financial Model agent | Calculation/model adapter feeding Beliefs |
| Next Action Planner | Experiment Optimizer + execution policy |
| Execution Strategy | Multi-horizon action policy |
| Startup Case Intelligence | Retrieval provider / case base |
| Memory Write | Event/evidence store + derived memory views |
| State Transition | Deterministic transition policy |
| Pydantic schema | Becomes executable domain contracts (retained and simplified) |
| Founder Diagnosis | Founder-state belief model |
| Matchmaking | Deferred network module; not core v0.1 |
| Business Plan Architect | Downstream projection of current state, never source of truth |

## Key deletion

“Agent” is no longer a primary domain object. It is an implementation detail for an inference function. This eliminates overlapping authority between Orchestrator, Routing, State Transition and specialist prompts.
