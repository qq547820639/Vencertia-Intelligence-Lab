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

## v1.1.0 — Intelligence Ingestion (2026-08-12)

### Added
- **Claim Binding pipeline** (`runtime/claim_binding.py`, `domain/binding.py`):
  ClaimExtractor → DeterministicClaimMatcher → EvidenceClaimLinker →
  ClaimBindingEngine; `UNBOUND_EVIDENCE` explicit status; candidate validation.
- **Composition Root** (`container.py`, `providers/factory.py`): ApplicationContainer,
  ProviderBundle, `with_resilience` (timeout/rate-limit/invalid-JSON/schema/
  unavailable/empty/partial → structured ProviderError), provider registry.
- **Decision-relevant context** (`runtime/context_ranker.py`): ContextBundleV11
  (15 context classes), ContextRanker (10 weighted dimensions), SemanticRanker protocol.
- **Research pipeline** (`runtime/research_planner.py`, `research_stop.py`,
  `capabilities/research.py`): ResearchPlanner (impact-sorted questions),
  ResearchStopRule (8 signals → RESEARCH_MORE/SEARCH_EXHAUSTED/EXPERIMENT_REQUIRED).
- **Reliability engines**: EvidenceDedupEngine (fingerprint/source-family),
  ConflictEngine (contradiction + uncertainty raise), freshness discounts in
  EvidencePolicy, BeliefUpdateRecord + posterior_version, DecisionTrace +
  DecisionSensitivityEngine (flip thresholds + STRONG/FRAGILE),
  ConfidenceCalibrator (UNCALIBRATED honesty), CallRecorder (ProviderCallRecord,
  no prompt), ExperimentOptimizer criteria validation, PredictionLedger.correct().
- **API/CLI**: 8 new endpoints (research plan/run, evidence bind/bindings,
  decision sensitivity/trace, belief history, research trace) + CLI sub-commands.
- **Benchmark**: L0 +10 capability cases (36/36), L1 +5 metrics (N/A semantics),
  L2Runner prospective registry, OSSAdmissionExperiment, migration 0003_v1_1.sql.
- **Engineering**: ruff in dev extras, `.github/workflows/ci.yml`, `make lint/ci/release`.

### Changed
- `Settings` gains research_*/binding_*/dedup/freshness/sensitivity/
  context_rank_weights/provider_*/call_log_enabled knobs.
- `api.py`/`cli.py` wire through `build_container()` (single composition root).
- `/v1/solve` returns `SolveResultV11` (all v1.0 fields preserved).
- Duplicate docs merged to lowercase-canonical filenames.

### Notes / deviations
- `Settings.policy_version` default stays `"1.0"` to preserve the v1.0 prediction
  ledger contract; v1.1 policy identity carried by `BeliefUpdateRecord.policy_version="1.1"`.
- L1 v1.1 metrics are N/A until labeled data exists (never faked).
