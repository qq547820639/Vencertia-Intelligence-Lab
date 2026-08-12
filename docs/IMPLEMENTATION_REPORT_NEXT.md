# IMPLEMENTATION REPORT — v1.1（Intelligence Ingestion）

> 版本：1.1 · 作者：寇豆码（工程师）· 状态：完成
> 基线：v1.0（65 src 文件 / 174 tests / L0 26-26 / L1 6-6 / demo 闭环）

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
