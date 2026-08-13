# iteration-v1-1-2-2.md — Iter2: 全部 P1

> 作者：寇豆码（Engineer） · 日期：2026-08-12 · 上游：`docs/v1.1.2-design.md` Part C（P1-7..P1-13）

## Changes

| # | 变更 | 文件 |
|---|---|---|
| P1-7 | CallRecorder 接线：`create_provider_bundle(settings, recorder=None)`；`_Resilient*Provider(inner, settings, recorder=None)` 组合 Recording（record kind/provider/model/task_kind/retry_count/latency/success/error_type/tokens/cost）；container `call_recorder` property 接线；红线保持（不存 prompt/API key） | `providers/factory.py`、`container.py`、`runtime/observability.py` |
| P1-8 | `RoundSummary` + 真实信号：belief_delta（target-only）、source_quality（authority×verification 均值，无 applied→0.0）、claim_coverage（claim-based）、decision_sensitivity_signal（翻转→1.0 / distance-to-flip 缩减）、decision_change_prob=deprecated alias；solve/research_service 构造 RoundSummary | `runtime/research_stop.py`、`runtime/runtime.py`、`runtime/research_service.py` |
| P1-9 | OpportunityCostEngine 裁决 **B（Deferred）**：`Settings.opportunity_cost_enabled=False`；solve 尾部 opt-in 更新 hook（默认零行为变化）；文档标注 AVAILABLE ENGINE / NOT ACTIVE BY DEFAULT | `config.py`、`runtime/runtime.py` |
| P1-10 | Benchmark 语义：`policy_regression_pass_rate` / `decision_option_accuracy`（gold_option_id=None 排除分母）/ `decision_status_accuracy`；`decision_accuracy`=option accuracy 兼容别名；`chosen/best_utility: float\|None`；`compute_decision_regret` 无可用对 → None | `benchmark/metrics.py`、`benchmark/harness.py`、`benchmark/l0.py`、`benchmark/l1.py` |
| P1-11 | skip 修复：`test_candidate_validate_endpoint` 改确定性 fixture（显式创建 CandidateClaim）→ 0 skipped | `tests/test_api_v11.py` |
| P1-12 | 版本单一来源接线：FastAPI version=__version__；health `runtime_version`/`api_contract_version` + legacy 派生键；`.env.example` 全量 Settings；demo banner v1.1.2 | `api.py`、`.env.example`、`examples/demo_b2b_saas_mvp.py` |
| P1-13 | 文档事实修复：BASELINE_V1_1_RC:30 / OPERATIONS:72,205 / ITERATION_V1_1_RC_3:25 / IMPLEMENTATION_REPORT_V1_1_RC:41,47,128 的 "PG 门控" → 真实原因（test_api_v11.py:113 无 candidate）；历史文档头部加 HISTORICAL SNAPSHOT | `docs/*.md` |

## Tests before → after

| 项 | before | after |
|---|---|---|
| pytest | 393 passed / 0 skipped | 414 passed / 0 skipped（+21 integrity 测试） |
| CallRecorder | 未接线（无真实记录） | solve 后 `list_call_records(kind="model")` 非空；research 后 `kind="search"` 非空；失败调用 success=False + error_type 结构化 |

## Benchmark before → after

| 项 | before | after |
|---|---|---|
| L0 pass_rate | 1.0 | 1.0（不降；gate 用 pass_rate 口径不变） |
| L0 decision_option_accuracy | （旧 decision_accuracy 0.615385 被 NO_DECISION 自匹配污染） | `decision_option_accuracy=None`（L0 无 gold_option_id 标注 → 诚实 N/A）；`decision_status_accuracy=1.0` |
| L1 regret | 假 0.0 | **None（N/A）**（无 utility 标签） |
| CLAIM_BINDING | P1.0/R0.96/F1 0.9796 | 同基线 |

## Failures / Fix decisions

- **L0 `decision_accuracy` 语义变化**：旧 0.615385 把 "gold_option_id=None → NO_DECISION" 的 case 按匹配计入分母（自匹配膨胀）。新口径排除无标签 case；L0 的 26 个 decision case 全部用 gold_status/expected_abstain 门控（无 gold_option_id）→ option_accuracy 诚实为 None。**不违反 gate**（gate 用 pass_rate=1.0，不变）。
- **`search_cost` 信号形状**：从 int 改为 dict `{queries_executed, latency_ms}`（真实成本）；仅 test_research.py 检查 key 存在，无类型断言 → 兼容。
- **error_type**：`ProviderTimeoutError.error_type="TIMEOUT"`（结构化），测试断言接受 TIMEOUT/PROVIDER_TIMEOUT。
