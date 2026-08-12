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

## v1.1.1 — Release Candidate Hardening (2026-08-12)

> GAP-01~10 全部闭合；数字以最后一次干净回归为准（`docs/BASELINE_V1_0.md` 三状态表）。

### Added
- **BindingStatus 四态**（GAP-01）：`BOUND / AMBIGUOUS / REJECTED /
  UNBOUND_EVIDENCE`（`UNBOUND` 兼容别名）；绑定 trace 扩展
  （candidate_claim_ids / candidate_scores / selected_claim_ids / reason）；
  阈值进 Settings（binding_min_score / binding_ambiguity_margin /
  binding_reject_threshold）。
- **HttpSearchProvider**（GAP-02）：通用 HTTP 搜索 adapter（httpx），
  外部响应 normalize 为内部 `SearchResult`；`search_provider=mock|http`，
  `http` 无 URL 时启动 fail loud；10 种失败模式结构化分类；
  运行期失败记录 `PROVIDER_FAILED` 事件 + graceful degradation。
- **三档 Robustness**（GAP-03）：`ROBUST_DECISION / MODERATE_DECISION /
  FRAGILE_DECISION`（旧 `STRONG_DECISION` 兼容映射）；结合 margin +
  flip distance + critical uncertainty；阈值进 Settings。
- **Synthetic Claim Binding Benchmark**（GAP-04）：
  `benchmark/claim_binding.py` + `data/benchmarks/claim_binding_cases.json`
  （34 cases，14 类）；8 指标 + Coverage；零分母 → N/A；
  `make benchmark-binding` + `make benchmark-all`。
- **L1 三层协议统一**（GAP-05，P0）：`L1Case` / JSON Schema / template /
  `l1_cases.jsonl` 唯一 canonical contract；T0 三字段默认 `[]`（严禁从
  hindsight 回填）；leakage gate 拒绝未过审计 case。
- **docs/OPERATIONS.md**（GAP-06，18 节）；**docs/BASELINE_V1_0.md**
  （GAP-07，三状态不混数字）；**ADR-013**（GAP-08，外部研究 vs
  项目结果证据权威性不同）。

### Changed
- `DeterministicClaimMatcher` 阈值改用 `settings.binding_min_score`；
  `ClaimBindingInput` 支持 per-call GAP-01 覆盖。
- `create_search_provider` 改按 `settings.search_provider` 选择（不再依赖
  `model_provider`）；`Settings` 增加 search gateway 配置。
- `EventType.PROVIDER_FAILED`；`ResearchTrace.notes`。
- 文档数字统一（GAP-09）：README / DELIVERY / IMPLEMENTATION_REPORT 等以
  最后一次干净回归为准。

### Fixed
- 旧命名断言按规格更新（STRONG_DECISION→ROBUST_DECISION 等，规格驱动，
  非 benchmark 欺骗，见 `docs/ITERATION_V1_1_RC_1.md`）。
- 阈值边界浮点噪声（flip 恰在阈值上被误判 fragile → round(6dp) 稳定）。
- **BLOCKER-API-001**：`SQLiteRepository` connect 增加 `check_same_thread=False`，
  修复 `make api`（uvicorn）下默认 SQLite DSN 的跨线程
  `sqlite3.ProgrammingError` → 所有碰 DB 端点 HTTP 500 的问题；新增
  `tests/test_default_container_api_smoke.py` 默认容器 + TestClient 防回归。
- **MAJOR-CB-001**：`claim_binding` 的 top1/top2 歧义分差比较前 round(...,7)，
  修复 0.90-0.80=0.09999…98 < 0.10 浮点噪声误判 AMBIGUOUS（与 F6 同源）；
  QA xfail(strict) 测试转为正常通过。
- **MAJOR-DEP-005**：`pyproject.toml` dev deps 增加 `jsonschema>=4`，干净
  venv `pip install -e ".[dev]"` 后 pytest collection 不再因缺 jsonschema 失败。
- **MINOR-CB-002**：`BindingStatus.UNBOUND` 别名注释修正（code-level name
  alias，非 literal-value alias）。
- **MINOR-PR-003**：`http_search` 非 dict 数组 → EMPTY_RESULT 的行为在
  docstring 明确记录（非 SCHEMA_MISMATCH，非数据丢失）。
- **MINOR-L1-004**：leakage gate 为 authoring-time 标记制在
  `docs/BENCHMARK.md` 与 `l1.py` docstring 明确。

### Tests
- 新增 `tests/test_l1_contract.py`（12）、`tests/test_binding_status_v111.py`
  （10）、`tests/test_http_search_provider.py`（23）、
  `tests/test_sensitivity_robustness_v111.py`（9）、
  `tests/test_claim_binding_benchmark.py`（8）、
  `tests/test_default_container_api_smoke.py`（2，BLOCKER-API-001 防回归）。
- QA 轮新增 `tests/qa_v111/` 对抗套件（binding/benchmark/provider/sensitivity/
  decision/l1 edges）。
- 全量 pytest：见 `docs/BASELINE_V1_1_RC.md` 最终数字。

### Benchmarks
- L0：36/36（不退化）；L1：6/6 + leakage 拒绝；Synthetic Claim Binding：
  33/34 PASS + 1 KNOWN-LIMIT（CB-034 文档化局限）。

### Limitations
- CB-034：`the founder is reachable` 对 `Founder can reach enough ICPs for
  validation` 的 lexical recall 低于 extractor 阈值（0.6）→ 引擎欠绑定；
  已作为已知局限标记（BenchmarkCaseReview）。
- 确定性基线语义匹配仅词法近似；真实语义匹配需 ADR-006 准入的语义 adapter。
- 三 Provider adapter PASS 以 mock 基 + httpx MockTransport 测试为准。

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
