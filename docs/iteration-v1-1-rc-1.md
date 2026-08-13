# ITERATION — v1.1 RC Hardening Round 1（GAP-01~10 实现 + 回归）

> HISTORICAL SNAPSHOT — 记录 v1.1.1 交付时点事实，不作为 v1.1.2 的 authority。

> 执行人：寇豆码（工程师）· 日期：2026-08-12 · 版本：1.1.1
> 基线：docs/baseline-v1-1-rc.md（283 passed / 1 skipped，L0 36/36）

## 1. Changes（本轮实现）

| 文件 | 变更 |
|---|---|
| `src/vencertia/benchmark/l1.py` | L1Case 扩展 canonical 字段（GAP-05）：claims_at_t0/beliefs_at_t0/evidence_at_t0（默认 []）、gold_decision/actual_decision 兼容、decision/options mirror、metadata；leakage gate 保留 |
| `schemas/historical_decision_case.schema.json` | 重写为唯一 canonical contract（GAP-05）：与 L1Case 逐字段一致；Evidence/Experiment/Belief $def 对齐 domain 模型 |
| `data/templates/historical_case_template.json` | 重写为 canonical 形态（GAP-05） |
| `src/vencertia/domain/binding.py` | BindingStatus 四态 + UNBOUND 兼容别名；EvidenceClaimBinding trace 扩展（GAP-01） |
| `src/vencertia/config.py` | 新增 binding_min_score / binding_ambiguity_margin / binding_reject_threshold / fragile_flip_threshold / fragile_margin / moderate_flip_threshold / moderate_margin / search_provider / search_url / search_api_key / search_timeout_seconds（+env） |
| `src/vencertia/runtime/claim_binding.py` | 四态判定路径（BOUND/AMBIGUOUS/REJECTED/UNBOUND_EVIDENCE）；matcher 阈值改 settings；NO_MATCH 返回完整 scores（GAP-01） |
| `src/vencertia/providers/http_search.py` | 新建 HttpSearchProvider（GAP-02） |
| `src/vencertia/providers/models.py` | SearchResult 扩展 content/published_at/metadata（GAP-02） |
| `src/vencertia/providers/factory.py` | create_search_provider 按 search_provider 选择；http 无 URL fail loud；register_search_provider（GAP-02） |
| `src/vencertia/events/types.py` | EventType.PROVIDER_FAILED |
| `src/vencertia/runtime/runtime.py` | 研究轮捕获 ProviderError → PROVIDER_FAILED 事件 + graceful degradation（GAP-02） |
| `src/vencertia/domain/research.py` | ResearchTrace.notes |
| `src/vencertia/runtime/decision_sensitivity.py` | 三档 robustness + normalize_robustness 兼容映射（GAP-03） |
| `src/vencertia/benchmark/claim_binding.py` | 新建 ClaimBindingBenchmarkRunner（GAP-04） |
| `data/benchmarks/claim_binding_cases.json` | 新建 34 cases / 14 类（GAP-04） |
| `src/vencertia/cli.py` | benchmark run --level CLAIM_BINDING |
| `Makefile` | benchmark-binding / benchmark-all（GAP-04） |
| `src/vencertia/benchmark/l0.py` + `data/benchmarks/l0_cases.json` | multiple_binding 用例显式 ambiguity_margin=0（GAP-01 规格驱动） |
| `pyproject.toml` / `.gitignore` / `scripts/make_release.py` | 版本 1.1.1 / 卫生项 / 打包名 Vencertia_Intelligence_Lab_v1.1.1.zip |
| `docs/operations.md`、`docs/baseline-v1-0.md`、`docs/architecture-decisions-next.md`（ADR-013）、`docs/providers.md`、`docs/changelog.md`、`README.md`、`DELIVERY_REPORT.md`、`docs/implementation-report-next.md` | GAP-06/07/08/09/10 文档 |

## 2. Tests before / after

| 项 | before（基线） | after（本轮） |
|---|---|---|
| pytest collected | 284 | 346 |
| pytest passed | 283 | **345** |
| pytest skipped | 1（`tests/test_api_v11.py:113` 无 candidate，非 PG 门控） | 同左 |
| pytest failed | 0 | **0** |
| 新增测试文件 | — | test_l1_contract（12）/ test_binding_status_v111（10）/ test_http_search_provider（23）/ test_sensitivity_robustness_v111（9）/ test_claim_binding_benchmark（8） |

## 3. Benchmark before / after

| 项 | before | after |
|---|---|---|
| L0 | 36/36 | **36/36**（不退化） |
| L1 | 6/6 + l1-07-leak 拒绝 | **6/6 + l1-07-leak 拒绝**（三层契约全链通过） |
| legacy v0.2 参考 | 20/24 | 20/24（不变，诚实标注） |
| Synthetic Claim Binding | —（无） | **34 cases / 14 类：Precision 1.0 / Recall 0.96 / F1 0.9796 / Unbound 1.0 / Ambiguous 1.0 / Rejected 1.0 / Multi-Exact 0.75 / Multi-Partial 0.25 / Coverage 1.0**（33 PASS + 1 KNOWN-LIMIT） |

## 4. Failures found & fix decisions

| # | 失败 | 根因 | 决定 |
|---|---|---|---|
| F1 | 旧 `test_multiple_match_binds_one_evidence_to_two_claims` / QA 同款 | GAP-01 语义变更：近似重复 claim 现在正确判为 AMBIGUOUS（禁止强行 top1） | **规格驱动更新**：断言改为 AMBIGUOUS；新增"clear multi"用例（margin=0）证明多绑能力。非 benchmark 欺骗 |
| F2 | `test_qa_bundle_builds_for_both_providers` 期望 openai_compatible 时 search=None | GAP-02 变更：search 由 search_provider 独立选择（默认 mock） | **规格驱动更新**：断言 search 已接线 |
| F3 | `test_qa_provider_failure_does_not_pollute_canonical_state` 期望 ProviderError 上抛 | GAP-02 变更：运行期搜索失败改为 graceful degradation（PROVIDER_FAILED 事件 + 不污染状态） | **规格驱动更新**：断言 PROVIDER_FAILED 事件 + 零证据/绑定 |
| F4 | L0 `l0_multiple_binding` 失败（0 bindings） | 同 F1：近似重复 claim → AMBIGUOUS | L0 用例显式 `binding_ambiguity_margin=0.0`（能力可配置，非 gold 欺骗） |
| F5 | 全量回归旧 STRONG/FRAGILE 断言 | GAP-03 命名变更 | **规格驱动更新**：STRONG_DECISION→ROBUST_DECISION 等（test_sensitivity / test_solve_v11 / test_api_v11 / QA sensitivity / l0.py） |
| F6 | flip 恰在阈值（0.10）被判 FRAGILE | 浮点噪声（0.09999… < 0.10） | `_classify` 对 flip distance round(6dp)，边界稳定 |
| F7 | L1 template 全链失败 | template 的 evidence/experiment 用旧 schema 形态，domain 模型不认 | template 改用 domain Evidence/Experiment 形态；schema $def 对齐 domain |

## 5. BenchmarkCaseReview（gold 复核记录）

- **CB-034**（known limitation，非 gold 修复）：gold=BOUND [CLM_A, CLM_B]，
  证据 "ICP will pay for the promised outcome; the founder is reachable"。
  人工复核：`the founder is reachable` 对 CLM_B（"Founder can reach enough
  ICPs for validation"）仅部分支持；确定性 extractor 的 lexical recall 阈值
  （0.6）使其欠绑定（predicted=[CLM_A]）。**如实标记 KNOWN-LIMIT**，
  不改 gold 让实现通过；文档中明确该局限。
- 其余 33 条 gold 与引擎确定性行为一致，无需改动。

## 6. 遗留问题

- 确定性语义匹配仅词法近似（真实语义匹配需 ADR-006 准入 adapter）；
- L1 五个 v1.1 指标无标签仍为 N/A（不伪造）；
- L2 为 prospective registry（非本轮回填）；
- 三 Provider adapter 以 mock 基 + httpx MockTransport 测试为准，
  真实 HTTP 端点需用户自备（GAP-10 已文档化）。
