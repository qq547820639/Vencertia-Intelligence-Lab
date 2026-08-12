# ITERATION_V1_1_2_3.md — Iter3: P2 + 全量回归 + 发布闸门

> 作者：寇豆码（Engineer） · 日期：2026-08-12 · 上游：`docs/v1.1.2-design.md` Part D（P2-14..P2-17）

## Changes

| # | 变更 | 文件 |
|---|---|---|
| P2-14 | Repository private 调用清零：`context_ranker.py` 的 `repo._list` 由 P0-4 的 `list_actions/list_outcomes` 公开 API 消除；`test_runtime_never_calls_repository_private_list` 源码扫描断言 | `runtime/context_ranker.py`、`tests/test_integrity_v112.py` |
| P2-15 | 层依赖环修复：`ContextBundle`/`ContextBundleV11` 迁入 `domain/context.py`（DTO 放 domain，capability 契约）；runtime.context 保留 ContextBuilder 并 re-export；capabilities 8 文件改 import；research.py 的 ResearchPlanner 改 TYPE_CHECKING 惰性导入（顺带修 `import vencertia.capabilities` 独立导入环） | `domain/context.py`（新）、`runtime/context.py`、`runtime/context_ranker.py`、`capabilities/*.py` |
| P2-16 | SolveOrchestrator 拆分：facade 保留；提取 CompilationService / DecisionEvaluationService / OutcomeSettlementService（ResearchExecutionService 已在 IT1-T04）；EngineBundle 新增 4 个 service 字段（additive）；API/CLI 签名不变、SolveResult/OutcomeRecordedResult schema 不变、持久化数据可读 | `runtime/compilation_service.py`（新）、`runtime/decision_evaluation_service.py`（新）、`runtime/outcome_settlement_service.py`（新）、`runtime/runtime.py`、`runtime/__init__.py` |
| P2-17 | 事务边界：SQLite/Postgres `_store`/`_append_event`/`_delete`/`save_binding`/`save_belief_update_record` 在 `in_transaction` 内不提前 commit（深度计数）；research round mutation batch 包事务（solve 循环 + run_plan）；outcome settlement 全链包事务；失败整体 rollback | `repositories/base.py`、`repositories/sqlite.py`、`repositories/postgres.py`、`runtime/runtime.py`、`runtime/research_service.py`、`runtime/outcome_settlement_service.py` |
| 迁移 | `scripts/backfill_evidence_project_ids.py`：存量 PROJECT/CUSTOMER 证据按 claim_ids→claims.project_id 回填；无法解析保持 None（UNASSIGNED，读边界不进入任何项目上下文） | `scripts/backfill_evidence_project_ids.py`（新） |
| 文档 | README/DELIVERY 数字更新（417 / 0 skipped）；BASELINE_V1_1_2.md 更新为最终数字；三份 ITERATION_V1_1_2_{1,2,3}.md | `README.md`、`DELIVERY_REPORT.md`、`docs/*.md` |

## Tests before → after（拆分前后比对）

| 项 | before（Iter2 末） | after（Iter3） |
|---|---|---|
| pytest | 414 passed / 0 skipped | **417 passed / 0 skipped**（+3 P2-17 原子性测试） |
| 拆分行为比对 | 基线快照 414 passed | 拆分后 417 passed（含 3 个新增原子性测试；无行为回归） |

## Benchmark（最终）

| 项 | 值 |
|---|---|
| L0 | 36/36 pass_rate 1.0（不降） |
| L1 | 6/6（不降） |
| CLAIM_BINDING | P 1.000 / R 0.960 / F1 0.979592 / Unbound 1.0 / Ambiguous 1.0 / Rejected 1.0 |

## Release Gate A–J 收口

- **A tests**：417 passed / **0 skipped**（0 failed）。
- **B L0**：36/36 pass_rate 1.0（36/36 不降）。
- **C L1**：6/6 cases 不退化。
- **D Binding**：P≥1.0 / R≥0.96 / F1≥0.9796 —— 不靠改 gold 退化。行为变化 comparison：见下方说明。
- **E 隔离**：`test_project_evidence_does_not_leak_between_projects` PASS（写边界 ValueError + 读边界过滤 + Context 不含他项目证据）。
- **F Research API 闭环**：`test_research_api_applies_evidence_and_updates_belief` PASS（applied evidence 落库 + belief 变化 + project_id 归属）。
- **G Experiment validation**：`test_invalid_experiment_never_persisted` / `provider_generated_vague_experiment_is_rejected` / `default_experiment_passes_validator` PASS。
- **H Provider observability**：`test_call_recorder_records_real_provider_calls` PASS（model/search 记录 + 失败记录 + 红线无敏感字段）。
- **I SQLite+PG contract parity**：`list_evidence/list_actions/list_outcomes` 在 EntityStoreMixin 实现（三后端自动 parity）；`test_repository_public_action_outcome_queries` InMemory+SQLite parity PASS；PG 深度计数同语义（DSN-gated，无环境则文档说明）。
- **J 文档版本一致**：README/DELIVERY/BASELINE_V1_1_2 = 1.1.2 / 417 / 0 skipped；`test_version_single_source` PASS。

## Comparison report（Release Gate D 语义变化）

| 行为变化 | 说明 |
|---|---|
| P0-3 写边界 | PROJECT/CUSTOMER 证据无 project_id → ValueError（API 400）。测试 fixture 已机械补 project_id。存量库用 `scripts/backfill_evidence_project_ids.py` 回填；无法解析 → UNASSIGNED（不进入任何项目上下文）。 |
| P0-3 读边界 | 项目 Context 不再全库读证据；只读 project-owned + 显式共享（WORLD/MARKET/COMPANY_CASE with project_id=None）。这是 P0-3 的修复目标（消除跨项目串扰），语义变化符合规格。 |
| P0-5 /v1/research/run | 端点从"只存 trace"升级为"完整 pipeline + 落库 applied evidence/beliefs"（additive 响应）。破坏性仅在于端点此前不产生证据——正是被修复的缺陷。 |
| P0-6 实验校验 | 所有入口过同一 validate_experiment；无 criteria/模糊 action 的实验不再进 ranked/落库。L0/L1 benchmark 输入实验数据已补 criteria（gold 未动）。 |
| P1-10 L0 decision_accuracy | 旧值 0.615385 被 NO_DECISION 自匹配污染；新口径排除无 gold_option_id case（L0 用 status 门控 → option_accuracy=None）。gate 用 pass_rate，不降。 |
| P1-10 L1 regret | 假 0 → None（N/A）。 |

## Failures / Fix decisions

- **B023（ruff）**：事务闭包引用循环变量 → 用默认参数绑定（`_state=state, _trace=trace, ...`）显式捕获当前迭代值（闭包在 in_transaction 内同步执行，语义正确）。
- **`import vencertia.capabilities` 独立环**（基线即存在）：`capabilities.research → runtime.research_planner → runtime.runtime → capabilities`。P2-15 顺带将 ResearchPlanner 改为 TYPE_CHECKING 惰性导入 → 两种导入顺序都可用。
