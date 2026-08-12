# Baseline — Vencertia v1.1 Release Candidate

> HISTORICAL SNAPSHOT — 记录 v1.1.1 交付时点事实，不作为 v1.1.2 的 authority。

> 本轮（v1.1 RC Hardening）唯一基线记录。
> 创建时间：2026-08-12 · 执行人：主理人（齐活林）团队

## 1. Source Provenance

```text
SOURCE_PROVENANCE = 本地 git 工作区（GitHub 远程 main 已同步）
GIT_SHA          = e6cd82d9f7138e901a759f0e209f86cb51f90173
BRANCH           = main
REMOTE           = git@github.com:qq547820639/Vencertia-Intelligence-Lab.git
WORKTREE         = clean（0 未提交改动）
```

## 2. 运行环境

```text
Python      = 3.13.12（managed venv）
Package     = vencertia-decision-runtime 1.1.0
PYTHONPATH  = src
```

## 3. 冻结时基线数据（真实运行）

| 项 | 值 |
|---|---|
| pytest collected | 284 |
| pytest passed | 283 |
| pytest skipped | 1（`tests/test_api_v11.py:113` — no candidate claims generated in this scenario，非 PG 门控） |
| pytest failed | 0 |
| L0 total | 36 |
| L0 passed | 36 |
| L0 failed | 0 |
| L0 pass_rate | 1.0 |

## 4. Git 最近 5 个提交

```text
e6cd82d docs(v1.1): final delivery report (10-section)
600a6d9 fix(v1.1): L2 registry path resolved to repo root (parents[3]); remove stray src/data artifact
8a07cd7 feat(v1.1): Intelligence Ingestion — Claim Binding + Research Runtime + Composition Root
b0f0b63 feat(v1.0): Vencertia Adaptive Decision System — deterministic decision runtime
a5fc40e docs: enhance README with TOC, target users, workflow diagram and prediction example
```

## 5. 三个 Baseline 状态区分（科学准确，不混数字）

| 状态 | 时间 | tests | L0 | 说明 |
|---|---|---|---|---|
| v1.0 reported | 2026-08-12 早 | 174 passed | 26/26 | v1.0 交付时记录（docs/IMPLEMENTATION_REPORT.md） |
| v1.1 pre-RC | 2026-08-12 10:00 | 283 passed / 1 skipped | 36/36 | v1.1 主体交付（docs/IMPLEMENTATION_REPORT_NEXT.md） |
| **v1.1 RC（本轮）** | **2026-08-12 10:49** | **283 passed / 1 skipped** | **36/36** | 本文档，Gap Closure 起点 |

## 6. 已知 Gap（本轮 10 项，见 TASK/规格）

```text
GAP-01 BindingStatus 缺 AMBIGUOUS / REJECTED
GAP-02 缺真正 HttpSearchProvider
GAP-03 Robustness 只有两级
GAP-04 缺独立 Claim Binding Benchmark
GAP-05 L1 Python Model / JSON Schema / Template 协议漂移（最高优先级）
GAP-06 缺 docs/OPERATIONS.md
GAP-07 缺完整 Baseline 文档体系（BASELINE_V1_0.md）
GAP-08 缺 ADR-013
GAP-09 README / Delivery / Implementation 测试数字漂移
GAP-10 Search 文档描述与实际实现不一致
```

> 本 Baseline 冻结后，任何修改生产代码前以此为准。最终数字只以最后一次干净回归为准（GAP-09）。
