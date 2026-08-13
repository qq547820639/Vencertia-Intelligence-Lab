# Evidence Pipeline（v1.1）

> 版本：1.1 · 施工：T02/T04

## 流水线

```
Search/Retrieval → SearchAdapter（fingerprint/canonical_source/source_family）
  → EvidenceDedupEngine（精确去重 + 相似组共享 independence_group）
  → ClaimBindingEngine（绑定级 scope 门）
  → EvidencePolicy（authority × verification × freshness 折扣）
  → BeliefEngine（有效权重进入 pseudo-count / prior-only）
  → ConflictEngine（支持+反驳均超阈值 → EvidenceConflict + uncertainty 抬升）
```

## Dedup

- **精确去重**：`content_fingerprint = sha256(归一化文本)`；同 fingerprint 只留
  canonical（authority 最高），其余 drop（不持久化）。
- **同 source family 相似**：lexical overlap ≥ `dedup_similarity_threshold`
  共享 `independence_group` → BeliefEngine 既有折减（`1/(1+index)`）生效。
- `DedupResult`：`groups` / `dropped_ids` / `kept_ids`。

## Freshness

`Evidence` 新增可选字段：`published_at / valid_from / valid_until / freshness_score`。

`EvidencePolicy.freshness_factor(e, now)`：
- `now > valid_until` → 0.0
- `now ∈ [valid_from, valid_until]` → 1.0
- 无有效期 → 1.0
- 否则 `exp(-age_days / freshness_half_life_days)`

`grade()` 的 `effective_weight` 乘 freshness；`EvidenceGrade.freshness_discount` 记录。

## Conflict

`ConflictEngine.detect(evidence_by_claim, threshold)`：同 claim 支持权重与反驳权重
均 ≥ threshold → `EvidenceConflict(severity>0, resolution_status=OPEN)` 持久化。
`apply_to_belief()` 把 `uncertainty += 0.15 × severity`（封顶 1.0），
并在对应 `BeliefUpdateRecord.conflict_uncertainty_raise` 中记录。

## Scope 隔离（v1.0 不变式延续）

Company Case 证据不得直接改项目 WTP；绑定级矩阵见 `docs/claim-binding.md`。
