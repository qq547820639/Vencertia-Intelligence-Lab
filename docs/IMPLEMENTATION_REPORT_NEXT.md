# IMPLEMENTATION REPORT — v1.1（Intelligence Ingestion）

> HISTORICAL SNAPSHOT — 记录 v1.1.1 交付时点事实，不作为 v1.1.2 的 authority。

> 版本：1.1 · 作者：寇豆码（工程师）· 状态：完成
> 基线：v1.0（65 src 文件 / 174 tests / L0 26-26 / L1 6-6 / demo 闭环）
>
> **后续更新（GAP-09）**：本文档是 v1.1 pre-RC 的历史记录（283 passed /
> 1 skipped）。v1.1.1 RC Hardening 的最终数字见
> `docs/IMPLEMENTATION_REPORT_V1_1_RC.md`（345 passed / 1 skipped，
> L0 36/36，Synthetic Claim Binding Benchmark 8 指标）。
> 历史数字与最终数字按状态区分，不混用（`docs/BASELINE_V1_0.md`）。

## 1. 交付摘要

| 项目 | v1.0 | v1.1 |
|---|---|---|
| src 文件数 | 65 | 85（+20：domain×6 / runtime×8 / providers factory+errors / container / benchmark l2+oss_admission / migrations 0003） |
| 测试文件数 | 20 | 27（+7：claim_binding / research / dedup / conflict / sensitivity / container / observability / l2 / solve_v11 / api_v11 / v11_extra） |
| pytest | 174 passed | **245 passed / 1 skipped** |
| L0 | 26/26 | **36/36**（26 v1.0 + 10 能力用例，pass_rate 1.0，无回归） |
| L0 legacy 参考 | 20/24 | 20/24（不变，人工 gold 偏差如实保留） |
| L1 | 6/6 | **6/6**（+1 泄漏拒绝不变；5 个新指标无标签 → N/A 不伪造） |
| demo | 闭环 | 闭环（40 events） |
| ruff | — | **All checks passed** |
| CLI/API import | OK | OK |

## 2. 三轮迭代记录（详见 `docs/ITERATION_LOG.md` v1.1 节）

- **Iter1 Wiring**（T01→T03）：Composition Root + Provider 韧性 + 领域扩展 +
  ClaimBinding + ResearchPipeline + /solve 闭环。全量测试 174 不回归。
- **Iter2 Reliability**（T04）：dedup / conflict / freshness / belief trace /
  sensitivity / experiment criteria 强制 / prediction correct + 8 API 端点 + CLI。
- **Iter3 Learning**（T05）：L0 能力用例 + L1 新指标（N/A）+ L2 prospective +
  OSS admission + CallRecorder + ruff/CI + 文档合并 + 发布。

## 3. 关键设计决策（与施工图一致）

1. `Settings.policy_version` 默认保持 `"1.0"`（**偏差说明**）：v1.0 测试契约
   `test_register_creates_snapshot` / `test_stratified_scopes` 硬编码 `"1.0"`；
   直接改默认会回归 174 基线。v1.1 政策身份由新记录类型承载
   （`BeliefUpdateRecord.policy_version="1.1"`），并可用 `VENCERTIA_POLICY_VERSION=1.1` 切换。
2. `ExperimentOptimizer.propose()` 保持 v1.0 语义（可排序全部候选）；
   criteria 强制由 `validate_experiment()` 承担（或chestrator/API 在状态变更前调用），
   同时满足 v1.0 `test_propose_contract` 与 v1.1 "缺 criteria 被拒"。
3. `/health` 保持 `version="1.0.0"`（v1.0 测试契约）+ 新增 `api_version="1.1.0"`。
4. 绑定流水线默认 deterministic（token recall + `_WORD_FAMILY` 词形归一化），
   无向量库依赖；`SemanticClaimMatcher` / `SemanticRanker` 仅留 Protocol。

## 4. 遗留问题（诚实记录）

1. **L1 新指标无标签数据**：`claim_binding_accuracy / research_efficiency /
   evidence_yield / belief_delta_quality / decision_change_precision` 在 L1 报告
   中均为 `None`（渲染 N/A）——需要真实或标注数据后才可计算。
2. **CandidateClaim VALIDATED 路径**：v1.1 提供 API 标记
   （`POST /v1/claims/candidates/{id}/validate`）；人工评审 UI 不在本版本。
3. **UNBOUND_EVIDENCE 自动重试**：默认需用户重调 `/v1/evidence/bind`；
   `binding_auto_retry=False` 未启用自动重试。
4. **openai_compatible 无真实密钥**：仅构造测试；调用失败走结构化错误，
   未接入真实 API（符合"不真调外部 API"约束）。

---

## 5. 最终交付报告（主理人汇编，10 节）

### 5.1 Baseline（开发起点）
- tests：174 passed / 1 warning（v1.0）
- L0：26/26（pass_rate 1.0）；L1：6/6 + rejected l1-07-leak
- 已知断链：`runtime.py:587` 等 3 处 `claim_ids=[]` → Research Evidence 不绑 Claim → Belief 不变 → Decision 不变（P0-1 实证）；API/CLI 双装配 MockProvider（P0-2）；Makefile 硬编码开发机 PYTHON 路径

### 5.2 Iteration 1（Wiring）— 实际发现与修改
- 实现：providers/factory.py + container.py（Composition Root）、ClaimBindingEngine 四段流水线、DecisionRelevantContextBuilder 入 solve、ResearchPlanner、ResearchStopRule、solve 闭环重构
- 发现的问题：providers 循环导入（→ errors.py 拆分）；绑定初始全 UNBOUND（→ token recall + _WORD_FAMILY 词形归一化）；linker scope 传参错误（→ claim_id→scope 映射闭包）；多轮重复应用（→ 跨轮 fingerprint 过滤）
- 指标：v1.0 174 零回归；L0 26/26 保持

### 5.3 Iteration 2（Reliability）— 新问题与修复
- 实现：EvidenceDedupEngine、ConflictEngine、freshness 折扣、BeliefUpdateRecord + posterior_version、DecisionTrace + SensitivityEngine、ConfidenceCalibrator、8 个新 API 端点、CLI 增强
- 发现的问题：v1.0 propose 测试与"缺 criteria 被拒"冲突（→ propose 保持 v1.0 语义，validate_experiment 承担强制）；prediction correct 覆盖原记录（→ 新 id PRD_#vN）；CLI sensitivity 传错 convergence_status（→ NOT_CONVERGED）
- 指标：L0 36/36（+10 能力用例）；API/CLI smoke 通过

### 5.4 Iteration 3（Learning）+ QA 对抗轮
- 实现：L2 prospective registry（register/settle/due）、L1 新 5 指标（N/A 诚实）、OSSAdmissionExperiment、ProviderCallRecord 可观测性、CI（ruff+pytest+benchmark+smoke）、文档 7 份 + ADR-008~012、Makefile 清理、.gitignore 追加、release 目标
- QA Round 1 抓到 2 个 MAJOR（dedup 同族折减断裂 / 空 source 哈希碰撞静默丢证）→ 根因修复 → QA 38/38 转绿 → Round 2 PASS
- 主理人收尾修复：L2_SCHEMA_PATH parents[2]→parents[3]（src/data 垃圾路径）

### 5.5 最终架构（目录树见仓库，85 src 文件）
REALITY 不变（+EvidenceClaimBinding/BeliefUpdateRecord/ResearchPlan/ResearchTrace/DecisionSensitivity/EvidenceConflict 持久化）→ DECISION INTELLIGENCE（+ClaimBindingEngine/ResearchPlanner/ResearchStopRule/EvidenceDedupEngine/ConflictEngine/SensitivityEngine/ConfidenceCalibrator）→ CAPABILITY（Provider Factory + ApplicationContainer 统一装配）

### 5.6 真实 /v1/solve 数据流
Context→Compiler→CriticalUnknown→ResearchPlanner→Search/Retrieval→ClaimBinding（UNBOUND 显式）→EvidencePolicy→BeliefUpdate（trace+version）→StopCheck→Uncertainty→Convergence→DecisionEngine→Sensitivity→CONVERGED?Recommendation : SEARCH_CAN_HELP?Continue : ExperimentOptimizer→PredictionLedger→Persist→14 段标准输出

### 5.7 Benchmark 状态
- L0：36/36（synthetic regression，软件行为回归门）
- L1：6/6 + 1 泄漏拒绝（time-sliced；新 5 指标缺标签 → N/A）
- L2：schema + registry 已建（prospective，未来真实结算为校准最终 Truth）

### 5.8 Limitations（真实未完成）
- 真实 Web Search/LLM 未调用（mock 默认；openai_compatible 仅构造测试——"Adapter implemented, live provider unavailable without credentials"）
- L1 新指标需标注数据积累；CandidateClaim 人工评审 UI 未做（API 标记 VALIDATED 已有）；UNBOUND 自动重试默认关
- PG 未实跑（DSN 门控安全）；L2 无真实预测样本

### 5.9 Next Three Highest-ROI（按 Benchmark potential）
1. 真实 Research/LLM 适配器接入（ProviderCallRecord 已就绪，接真实 provider 后 L1/L2 数据开始积累）
2. L1 标注案例集扩充（Claim Binding Accuracy 等 5 指标从 N/A 变可计算）
3. L2 真实预测登记 → 校准重标定启用（Calibration 闭环的最终证据）

### 5.10 Final Deliverables
- repo：github.com/qq547820639/Vencertia-Intelligence-Lab（main=600a6d9）
- release：Vencertia_Decision_Runtime_v1.1.zip（378 files，独立可运行）
- test report：283 passed / 1 skipped（含 QA 对抗 38）
- benchmark report：L0 36/36 + L1 6/6 + legacy 20/24 参考
- implementation report：本文档 + docs/ITERATION_LOG.md v1.1 节
