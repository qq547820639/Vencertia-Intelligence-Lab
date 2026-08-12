# Baseline — Vencertia v1.0（历史基线，仅作对照）

> 本文件**区分三个 Baseline 状态**，数字不混用（GAP-07）。
> 唯一现行基线是 `docs/BASELINE_V1_1_RC.md`；本文档只做历史对照。

## 1. 三个状态（科学准确，不混数字）

| 状态 | 时间 | pytest | L0 | 说明 |
|---|---|---|---|---|
| **v1.0 reported** | 2026-08-12 早 | **174 passed / 0 failed** | **26/26** | v1.0 交付时记录（docs/IMPLEMENTATION_REPORT.md） |
| **v1.1 pre-RC** | 2026-08-12 10:00 | **283 passed / 1 skipped** | **36/36** | v1.1 主体交付（docs/IMPLEMENTATION_REPORT_NEXT.md） |
| **v1.1 RC final** | 2026-08-12（本轮） | **390 passed / 1 skipped** | **36/36** | GAP-01~10 完成后最后一次干净回归（docs/IMPLEMENTATION_REPORT_V1_1_RC.md） |

> 规则：任何文档引用测试数字必须标注所属状态；不得把 v1.0 的 174 与
> v1.1 的 283 混在同一句话里表述为同一版本的数字。

## 2. v1.0 基线明细（历史）

```text
Package     = vencertia-decision-runtime 1.0.0
Python      = 3.13.12（managed venv）
PYTHONPATH  = src
pytest      = 174 passed, 0 failed
L0          = 26/26（pass_rate 1.0）
L1          = 6/6（泄漏案例被正确拒绝）
legacy v0.2 = 20/24（诚实标注）
```

## 3. v1.1 pre-RC 基线明细（历史）

```text
Package     = vencertia-decision-runtime 1.1.0
pytest      = 283 passed, 1 skipped（PG 门控）, 0 failed
L0          = 36/36（26 v1.0 + 10 capability）
L1          = 6/6（l1-07-leak 被 leakage gate 拒绝）
legacy v0.2 = 20/24（不变，诚实标注）
```

## 4. 用途

- 供回归对比：任何新版本必须证明 **v1.0 174 / v1.1-pre-RC 283 未回归**；
- 供文档数字核对（GAP-09）：README / DELIVERY / IMPLEMENTATION_REPORT 引用
  数字时必须与对应状态一致；
- 禁止用早期数字冒充新版本数字，也禁止用新版本数字改写历史记录。
