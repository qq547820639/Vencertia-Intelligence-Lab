# iteration-v1-1-2-1.md — Iter1: 全部 P0（Runtime Integrity 语义断点修复）

> 作者：寇豆码（Engineer） · 日期：2026-08-12 · 基线：3bf22c8（390 passed / 1 skipped）
> 上游：`docs/v1.1.2-design.md` Part B（P0-1..P0-6）

## Changes

| # | 变更 | 文件 |
|---|---|---|
| P0-1 | `_build_context(project, request, decision=None)` 新增 decision 参数；solve post-compile 传 `compiled.decision` | `runtime/runtime.py` |
| P0-2 | `_decision_relevance(evidence, decision, claim_by_belief)` 走 Belief→claim 映射；删除 `{f"CLM_{r}"}` 字符串猜测；无 mapping 降级 0.5 | `runtime/context_ranker.py` |
| P0-3 | `Evidence.project_id/company_id`；`EntityStoreMixin.add_evidence` 写边界（PROJECT/CUSTOMER 必须 project_id）；`list_evidence(claim_ids, project_id, include_shared)` 读边界；ContextBuilder/DecisionRelevantContextBuilder 只读 project 域；research 证据 project_id=当前项目；record_outcome 证据 project_id=action.project_id；API add_evidence 推导/400 | `domain/evidence.py`、`repositories/base.py`、`runtime/context.py`、`runtime/context_ranker.py`、`runtime/runtime.py`、`runtime/claim_binding.py`、`runtime/research_service.py`、`api.py`、`cli.py`、`legacy/import_v10_2.py` |
| P0-4 | Repository Protocol 扩展 `list_actions(project_id, decision_id, experiment_id)` + `list_outcomes(project_id, action_id)`（三后端 parity）；recent_outcomes 走公开 API；删除 `repo._list` | `repositories/base.py`、`runtime/context_ranker.py` |
| P0-5 | 新建 `ResearchExecutionService`（单 pipeline）；solve/`/v1/research/run`/CLI `research run` 三路共享；API/CLI 不再丢弃 candidate evidence | `runtime/research_service.py`（新）、`runtime/runtime.py`、`api.py`、`cli.py`、`runtime/__init__.py` |
| P0-6 | `ExperimentProposalOutput.rejected`（additive）；`propose()` 内 enforce `validate_experiment`；default experiment 过同一 validator；solve rejected 进 decision trace notes；`DecisionTrace.notes` 新增 | `runtime/experiment_optimizer.py`、`runtime/runtime.py`、`api.py`、`cli.py`、`domain/decision_trace.py` |
| 地基 | `in_transaction` 深度计数（SQLite/Postgres `_store` 事务内不提前 commit） | `repositories/base.py`、`repositories/sqlite.py`、`repositories/postgres.py` |
| 版本 | `__version__="1.1.2"`、`__api_contract_version__="1.1"`；pyproject 1.1.2；FastAPI version 动态；health 新键 | `__init__.py`、`pyproject.toml`、`api.py` |
| 测试 | fixture 机械补 project_id；L0/L1 benchmark 实验补 criteria（输入数据，非 gold）；skip 修复（确定性 fixture） | `tests/*`、`data/benchmarks/l0_cases.json`、`data/benchmarks/l1_cases.jsonl` |

## Tests before → after

| 项 | before | after |
|---|---|---|
| pytest | 390 passed / 1 skipped | 393 passed / 0 skipped（Iter1 完成时） |
| 新增 P0 验收 | — | P0-1..P0-6 各验收测试绿（详见 `tests/test_integrity_v112.py`） |

## Benchmark before → after

| 项 | before | after |
|---|---|---|
| L0 | 36/36 pass_rate 1.0 | 36/36 pass_rate 1.0（不降） |
| L1 | 6/6 | 6/6（不降） |
| CLAIM_BINDING | P 1.000 / R 0.960 / F1 0.979592 | 同基线（P 1.0 / R 0.96 / F1 0.979592） |

## Failures / Fix decisions

- **语义变化（P0-3 写边界）**：PROJECT/CUSTOMER 证据无 project_id 现在 ValueError（API 400）。测试 fixture 机械补 project_id（`test_repositories.py`、`test_context.py`、`qa_capability_isolation.py`、demo）。Release Gate D comparison report 见 Iter3 收口。
- **API `/v1/research/run` 响应升级**：从 `[trace...]` 变为完整 `ResearchExecutionResult`（additive，traces 保留在 result 内）——这正是 P0-5 要修的缺陷（端点此前只存 trace）。
- **L0/L1 benchmark 实验数据**：propose() enforce 后，无 criteria 的实验被拒。已将 benchmark case 的 experiment 输入数据补上 action/success/failure/ambiguity（**gold 标签未动**，仅输入数据满足 v1.1.2 完整性规则）。
- **决策**：`solve` 主循环保留原处理顺序（dedup/binding/belief/stop），仅把 search/retrieval 委托 ResearchExecutionService（`run_solve_round`）；API/CLI 走 `run_plan` 完整 pipeline。行为 393 测试全绿证明无回归。
