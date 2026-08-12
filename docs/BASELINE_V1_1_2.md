# Baseline — Vencertia v1.1.2 Runtime Integrity Hardening

> 创建：2026-08-12 · 执行人：主理人（齐活林）团队
> 上游：v1.1.1 RC（3bf22c8，已推送）

## 1. Source Provenance

```text
SOURCE_PROVENANCE = 本地 git 工作区（远程 main 已同步）
GIT_SHA          = 3bf22c8（v1.1.1 基线）→ v1.1.2 工作区（本文件为最终数字）
BRANCH           = main
WORKTREE         = v1.1.2 全部实现已落盘（未提交）
Package          = vencertia-decision-runtime 1.1.2
Python           = 3.13.12
```

## 2. 冻结基线（v1.1.1 → v1.1.2 最终数字，真实运行 2026-08-12）

| 项 | v1.1.1 基线 | v1.1.2 最终 |
|---|---|---|
| pytest collected | 391 | 417 |
| pytest passed | 390 | **417** |
| pytest skipped | 1 | **0** |
| pytest failed | 0 | 0 |
| **skip 真实原因** | `tests/test_api_v11.py:113: no candidate claims generated in this scenario`（非 PG 门控） | 已修复（确定性 fixture）→ 0 skipped |
| L0 | 36/36（pass_rate 1.0） | 36/36（pass_rate 1.0） |
| L1 | 6/6 | 6/6 |
| CLAIM_BINDING | P 1.000 / R 0.960 / F1 0.979592 / Unbound 1.0 / Ambiguous 1.0 / Rejected 1.0 | 同基线（P 1.000 / R 0.960 / F1 0.979592 / Unbound 1.0 / Ambiguous 1.0 / Rejected 1.0） |
| Integrity tests（14+） | — | 24/24 PASS（`tests/test_integrity_v112.py`） |

## 3. 本轮目标（v1.1.2 Runtime Integrity Hardening）

修复"测试全绿但实际调用链语义断点"（规格 40 节），P0 六项：

```text
P0-1 post-compile ContextBuilder 未获得当前 Decision（decision 尾部才保存）   → FIXED
P0-2 ContextRanker 直接比较 Evidence.claim_ids vs Decision.relevant_belief_ids → FIXED（belief→claim 映射）
P0-3 Evidence 无 project_id → 多项目上下文串扰（Release Blocker）              → FIXED（写/读边界）
P0-4 recent_outcomes 用 get_outcome(action.id)，但 Outcome.id(OUT_) != Action.id(ACT_) → FIXED（list_actions/list_outcomes）
P0-5 Research API/CLI 只取 trace 丢弃 candidate evidence → FIXED（ResearchExecutionService 单 pipeline）
P0-6 Experiment validate_experiment 未在 runtime 实际 enforce → FIXED（propose 内 enforce + default 校验）
```

P1：CallRecorder 接线 / ResearchStopRule 真实信号 / OpportunityCostEngine 裁决 B（Deferred）/ Benchmark 语义（L0 option/status 分离、L1 regret N/A）/ skip 修复 / 版本单一来源（1.1.2）
P2：Repository private 调用清理 / 层依赖环（capabilities→domain.context）/ SolveOrchestrator 拆分（4 services）/ 事务边界（P2-17）

## 4. Release Gate（A-J）— v1.1.2 收口

A tests 417 passed / **0 skipped** / 0 failed / B L0 36-36 不降 / C L1 6 cases 不退化 / D Binding P 1.0 R 0.96 F1 0.9796（behavior comparison 见 `docs/ITERATION_V1_1_2_3.md`）/ E 跨项目证据隔离 PASS / F Research API 闭环 PASS / G Experiment validation PASS / H Provider observability PASS / I SQLite+PG parity / J 文档版本一致（1.1.2）

## 5. 版本

1.1.2（禁止 1.2.0；v1.2 = Intelligence Competition）— `vencertia.__version__="1.1.2"`、`__api_contract_version__="1.1"`、pyproject 1.1.2、FastAPI version 动态读、health `runtime_version`/`api_contract_version` + legacy 派生键。
