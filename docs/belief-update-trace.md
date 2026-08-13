# Belief Update Trace（v1.1）

> 版本：1.1 · 施工：T02/T04

## BeliefUpdateRecord

每次 belief 更新（一批证据应用后）生成一条不可变记录：

```python
class BeliefUpdateRecord(VencertiaBaseModel):
    id: str                     # BUR_...
    belief_id: str
    claim_id: str
    old_probability: float
    old_uncertainty: float
    evidence_used: list[str]
    authority: str              # 批内最高 authority
    verification: str
    correlation_discount: float  # independence 折减（1/(1+index) 累积）
    scope_discount: float        # COMPANY_CASE prior-only 折减
    freshness_discount: float    # freshness 折扣（EvidencePolicy 提供）
    effective_weight: float      # Σ applied weight
    new_probability: float
    new_uncertainty: float
    conflict_uncertainty_raise: float  # ConflictEngine 抬升量
    update_method: str = "BETA_BERNOULLI"
    policy_version: str = "1.1"
    posterior_version: int
```

## Belief 版本化

`Belief` 新增：`posterior_version`（每次更新 +1）、`previous_snapshot`
（{probability, uncertainty, alpha, beta}，批内首次变更前快照）、
`last_evidence_batch_id`、`policy_version`。

## 持久化

- `repositories` 协议：`save_belief_update_record` / `list_belief_update_records`。
- SQLite 专表 `belief_update_records`（migration `0003_v1_1.sql`）。
- 由 orchestrator（状态变更唯一入口）落库；BeliefEngine 只产出记录，不写库。

## 数据源

`/v1/beliefs/{id}/history` 返回完整更新历史，供 **Belief Delta Quality**（L1）
指标计算（gold delta 对齐 MAE / direction agreement）。
