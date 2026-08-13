# Intelligence Ingestion（v1.1）

> 版本：1.1 · 作者：寇豆码（工程师）· 上游：`docs/v1.1-design.md` §4

## 1. 解决什么问题

v1.0 的最大缺口：`runtime.py` 中 `_research()` 为检索/搜索产生的 Evidence 写入
`claim_ids=[]` —— 研究证据与判断闭环"物理断裂"，从未影响 Belief，也无法评估
"证据绑得对不对"（无 Claim Binding Accuracy 数据源）。

v1.1 把外部智能的输出变成一条受控流水线：

```
Research Result → ClaimExtractor(候选) → ClaimMatcher(匹配) →
Candidate validation → EvidenceClaimLinker → EvidenceClaimBinding(BOUND|UNBOUND)
→ EvidencePolicy(scope/freshness/authority) → BeliefEngine(BeliefUpdateRecord)
```

## 2. 设计不变式（继承 v1.0 + ADR-008/012）

1. **LLM 输出不是真相**：外部输出一律 Candidate → Validation → 才可持久化。
2. **Evidence 不可变**：修正用 SUPERSEDE/新版本，不覆盖。
3. **UNBOUND_EVIDENCE 是显式状态**：不偷偷绑定；允许重处理（`retry_count`）。
4. **CandidateClaim 不得直接 canonical**：必须过 deterministic validation
   （非空 / scope 合法 / 长度界 / 与既有 claim 归一化去重 / 与同批候选去重）。
5. **绑定记录是 Claim Binding Accuracy 的唯一数据源**（L1 指标）。

## 3. 模块清单（新增/修改）

| 模块 | 职责 |
|---|---|
| `domain/binding.py` | EvidenceClaimBinding / CandidateClaim / ClaimMatchResult |
| `runtime/claim_binding.py` | ClaimExtractor / DeterministicClaimMatcher / EvidenceClaimLinker / ClaimBindingEngine |
| `repositories` | `claim_bindings` / `belief_update_records` 专表 + 17 个新协议方法 |
| `events/types.py` | RESEARCH_PLANNED / EVIDENCE_BOUND_TO_CLAIM / EVIDENCE_BINDING_REJECTED 等 |

## 4. 绑定四态

| 状态 | 说明 | 事件 |
|---|---|---|
| EXISTING_MATCH | 绑到既有 claim（可一证多绑） | EVIDENCE_BOUND_TO_CLAIM |
| MULTIPLE_MATCH | 1 evidence 绑 ≥2 claim | EVIDENCE_BOUND_TO_CLAIM × n |
| NO_MATCH | 候选 claim 过 validation 入库（PENDING） | 无（candidate 持久化） |
| UNBOUND_EVIDENCE | 无匹配证据显式标记（claim_id=None） | EVIDENCE_BINDING_REJECTED |

`binding_confidence = match_score × extraction_confidence`，低于
`settings.binding_confidence_threshold` → UNBOUND。

## 5. Scope 绑定矩阵

| Evidence scope | 可绑 Claim scope |
|---|---|
| COMPANY_CASE | COMPANY_CASE / WORLD / MARKET |
| PROJECT / CUSTOMER | PROJECT / CUSTOMER |
| MARKET / WORLD / FOUNDER | 任意 |

跨 scope → binding 被拒（`rejected_evidence`）。
