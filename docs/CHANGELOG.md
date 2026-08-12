# Changelog

## v1.0.0 — Vencertia Adaptive Decision System v1.0 (2026-08-12)

### Added (relative to v0.1 prototype)
- **Domain layer** (`src/vencertia/domain/`): pydantic v2 canonical objects
  (`extra="forbid"`, `validate_assignment`, `use_enum_values`) —
  Objective/Claim/Evidence/Belief/Decision/Experiment/Action/Outcome/
  PredictionEntry/CalibrationProfile/Founder/Memory/CompanyCase/Policy/
  Convergence, plus 25+ enums.
- **Deterministic engines** (`src/vencertia/runtime/`): EvidencePolicy (9-level
  authority + scope gates + LLM downgrade), BeliefEngine (Beta-Bernoulli
  pseudo-counts + conflict detection), UncertaintyEngine, DecisionEngine
  (EU + penalties + margin + ABSTAIN + 7 decision types), ConvergenceEngine
  (7-state machine), ExperimentOptimizer (EIG×Impact×Uncertainty÷Cost÷Time),
  PredictionLedger (tamper-evident snapshots), CalibrationEngine (Brier/ECE +
  ALL/MODEL/DOMAIN/MODULE stratification), OpportunityCostEngine, ContextBuilder,
  SolveOrchestrator (solve + outcome closed loop).
- **Persistence** (`src/vencertia/repositories/`): Repository protocol with
  optimistic locking (`StaleWriteError`), SQLite full implementation +
  migrations, PostgreSQL DSN-gated implementation, in-memory test repo.
- **Events**: EventBus + 17 event types + persistent event log (audit/replay).
- **Capabilities & providers**: ModelProvider/SearchProvider/RetrievalProvider
  protocols, deterministic MockProvider/MockSearch/MockRetrieval,
  OpenAICompatibleProvider (httpx), 8 capability modules (candidates only).
- **API/CLI**: FastAPI 14 endpoints (+health), typer 14-command CLI.
- **Benchmark**: L0 (26 synthetic cases + legacy 24 reference), L1 time-sliced
  with leakage audit, full metric set + comparison harness.
- **Legacy bridge**: V10.2 mapping tables + release importer (`migrate-v10.2`).

### Behavior changes
- Decision types are explicit (GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION/ABSTAIN).
- ABSTAIN always carries a ranked next experiment.
- Company-case evidence never moves project beliefs without transferability ≥ 0.6.
- Beliefs/evidence/decisions are versioned and concurrency-safe.

### Notes / known deviations
- `data/benchmarks/v0.2.jsonl` legacy gold labels: 4 of 24 are hand-authored
  judgment labels that the deterministic engine (v0.1 or v1.0) does not
  reproduce; kept as reference, not hard gate.
