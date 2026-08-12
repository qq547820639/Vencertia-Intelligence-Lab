# IMPLEMENTATION REPORT — v1.1 Release Candidate（GAP-01~10 全部闭合）

> 版本：1.1.1 · 作者：寇豆码（工程师）· 状态：RC 完成
> 日期：2026-08-12 · 基线：docs/BASELINE_V1_1_RC.md

## 1. Source Baseline

```text
GIT_SHA    = e6cd82d9f7138e901a759f0e209f86cb51f90173（基线起点，main）
WORKTREE   = 基线时 clean（除 docs/BASELINE_V1_1_RC.md）
Python     = 3.13.12（/Users/panhao/.workbuddy/binaries/python/envs/default/bin/python）
PYTHONPATH = src
Package    = vencertia-decision-runtime 1.1.0 → 1.1.1（禁止 1.2.0）
```

## 2. Gap Audit（10 项）

| Gap | 主题 | 状态 | 证据 |
|---|---|---|---|
| GAP-05 | L1 三层协议统一（P0） | **DONE** | L1Case ↔ schema ↔ template ↔ l1_cases.jsonl 唯一 contract；tests/test_l1_contract.py（12 条）；leakage gate 拒绝 l1-07-leak |
| GAP-01 | BindingStatus 四态 | **DONE** | BOUND/AMBIGUOUS/REJECTED/UNBOUND_EVIDENCE + UNBOUND 别名；trace 扩展；阈值进 Settings；tests/test_binding_status_v111.py（10 条，含 7 场景） |
| GAP-02 | HttpSearchProvider | **DONE** | providers/http_search.py；search_provider=mock\|http；无 URL fail loud；10 种失败模式；PROVIDER_FAILED 事件 + graceful degradation；tests/test_http_search_provider.py（23 条） |
| GAP-03 | Robustness 三级 | **DONE** | ROBUST/MODERATE/FRAGILE + 旧字符串兼容；阈值进 Settings；edge tests；tests/test_sensitivity_robustness_v111.py（9 条） |
| GAP-04 | 独立 Claim Binding Benchmark | **DONE** | benchmark/claim_binding.py + 34 cases/14 类；8 指标+Coverage；零分母 N/A；make benchmark-binding / benchmark-all；tests/test_claim_binding_benchmark.py（8 条） |
| GAP-06 | docs/OPERATIONS.md | **DONE** | 18 节，含环境变量全表 |
| GAP-07 | Baseline 文档 | **DONE** | docs/BASELINE_V1_0.md（三状态不混数字）；BASELINE_V1_1_RC.md 保留复核 |
| GAP-08 | ADR-013 | **DONE** | "Research Evidence and Project Outcome Evidence Have Different Authority"；明确 "External research cannot directly produce PROJECT_REALITY authority." |
| GAP-09 | 文档数字统一 | **DONE** | fresh run 后统一 README/DELIVERY/CHANGELOG/BASELINE/IMPLEMENTATION 数字（格式 X passed / Y skipped） |
| GAP-10 | Search 文档一致性 | **DONE** | PROVIDERS.md/OPERATIONS.md/DELIVERY_REPORT.md 写明 "Generic HTTP Search adapter implemented. No commercial search vendor is bundled. Live use requires user-supplied endpoint and credentials." |

## 3. Iterations

- **ITERATION_V1_1_RC_1.md**：实现 + 回归 + 失败/修复决定（F1~F7）+ BenchmarkCaseReview（CB-034）。
- ITERATION_V1_1_RC_2.md / _3.md：后续 QA 轮补充（工程师不写）。

## 4. Final Tests

```text
pytest collected : 391
pytest passed    : 390
pytest skipped   : 1（PG 门控，未配置 VENCERTIA_PG_DSN）
pytest failed    : 0
```

- 新增测试 64 条（6 个新文件，含 BLOCKER-API-001 防回归 smoke 2 条）；
  QA 轮另增 `tests/qa_v111/` 对抗套件；v1.0 174 / v1.1-pre-RC 283 零回归。
- skip 解释：`tests/test_v11_extra.py` 中 PG 依赖用例，无 DSN 时按设计跳过。
- 修复轮（QA NOT READY → 3 阻断项）后干净 venv 复验：**390 passed /
  1 skipped / 0 failed**（`/tmp/v111-fix-venv`，`pip install -e ".[dev]"`，
  jsonschema dev 依赖生效）。

## 5. L0

```text
new_l0     : 36 / 36 passed（pass_rate 1.0，不退化）
legacy v0.2: 20 / 24（不变，人工 gold 偏差如实保留）
```

## 6. Synthetic Claim Binding Benchmark

```text
level     : CLAIM_BINDING（SYNTHETIC —— NOT real-world accuracy）
cases     : 34（14 类全覆盖：single/multi/irrelevant/ambiguous/rejected scope/
            company case/project outcome/external research/LLM inference/
            contradiction/near duplicate/same keywords different meaning/
            weak lexical overlap/strong semantic relation）
precision                  : 1.0
recall                     : 0.96
f1                         : 0.9796
unbound_accuracy           : 1.0
ambiguous_accuracy         : 1.0
rejected_accuracy          : 1.0
multi_claim_exact_match    : 0.75
multi_claim_partial_match  : 0.25
coverage                   : 1.0
known limitations          : CB-034（extractor recall 阈值 0.6 导致欠绑定，已标记）
deterministic              : 完全可重复（tests/test_claim_binding_benchmark.py 断言）
```

## 7. L1

```text
三层契约 : L1Case（Python）↔ schemas/historical_decision_case.schema.json ↔
         data/templates/historical_case_template.json ↔ data/benchmarks/l1_cases.jsonl
         template→schema→model_validate→L1Runner 全链通过（test_l1_contract）
l1_cases : 7/7 三层通过；正式执行 6/6 passed
leakage  : l1-07-leak（leakage_audit_passed=false）被拒绝执行正式 L1 benchmark
向后兼容 : 旧 case 缺 T0 三字段默认 []（严禁从 future_outcome/hindsight_data 回填）
```

## 8. L2 Readiness

- L2 为 prospective registry（`benchmark/l2.py`），本轮未回填、不改 gold；
- 保持既有能力与测试（tests/test_l2.py 通过）。

## 9. Provider Status

| Provider | 状态 | 验证 |
|---|---|---|
| Mock（model/search/retrieval） | PASS | 全量测试 |
| OpenAI-compatible | PASS（构造级） | 未配 key 只 wire 不调用；resilience 结构化错误 |
| HTTP Search（GAP-02） | PASS（mock 基 + httpx MockTransport） | 10 种失败模式 + 成功 normalize + fail-loud + 无 DTO 泄漏 + 权限边界 |

运行期失败纪律：任何失败不产生伪 Evidence、不修改 canonical 状态、
记录 PROVIDER_FAILED 事件 + graceful degradation（SEARCH_EXHAUSTED），
不 silent fallback mock。

## 10. Legacy Compatibility

- legacy V10.2 import（migrate-v10.2 + `legacy/` mapping）：PASS
  （tests/test_legacy_import.py）。
- `BindingStatus.UNBOUND` 兼容别名保证旧持久化数据可读（GAP-01）。
- L0 legacy v0.2 参考 20/24 不变。

## 11. Known Limitations

1. CB-034：`the founder is reachable` 对 "Founder can reach enough ICPs for
   validation" 的 lexical recall < extractor 阈值 → 引擎欠绑定（文档化）。
2. 确定性基线语义匹配仅词法近似；真实语义匹配需 ADR-006 准入的语义 adapter。
3. L1 五个 v1.1 指标（Claim Binding Accuracy 等）无标签 → N/A（不伪造）。
4. 真实 HTTP 搜索端点需用户自备（未集成商业搜索服务，GAP-10）。
5. 三 Provider adapter 的 HTTP 路径以 MockTransport 测试为准，未做真实外呼。

## 12. Release Gate（10 项完成标准）

| # | Gate | 结果 |
|---|---|---|
| 1 | 全量 pytest 0 failed | ✅ 390 passed / 1 skipped（skip=PG 门控，已解释） |
| 2 | L0 ≥36/36 不退化 | ✅ 36/36 |
| 3 | binding benchmark 8 指标可输出 | ✅ 8 指标 + Coverage（Synthetic 标注） |
| 4 | L1 三层契约全过 + leakage 拒绝 | ✅ 6/6 + l1-07-leak 拒绝 |
| 5 | API smoke | ✅ test_api/test_api_v11 通过 + import OK |
| 6 | CLI smoke | ✅ test_cli 通过 + import OK |
| 7 | 三 provider adapter PASS | ✅ mock / openai_compatible / http（mock 基） |
| 8 | legacy V10.2 PASS | ✅ |
| 9 | CI 等价本地命令过 | ✅ ruff 0 error + pytest 全绿 + benchmark + smoke |
| 10 | 文档数字与代码一致 | ✅ 三状态区分（BASELINE_V1_0），README/DELIVERY/CHANGELOG 已统一 |

## 13. Final Release Decision

- **版本**：1.1.1（不是 1.2.0）。
- **结论**：**RELEASE CANDIDATE PASS** —— 10 项 Gap 全部闭合，
  全量回归 0 failed，L0 不退化，Synthetic Claim Binding Benchmark 可复现，
  文档与代码数字一致。等待 QA 轮（ITERATION_V1_1_RC_2/_3）后发布
  `make release` → `Vencertia_Intelligence_Lab_v1.1.1.zip`。
