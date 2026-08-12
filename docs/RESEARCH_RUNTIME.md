# Research Runtime（v1.1）

> 版本：1.1 · 关联：ADR-011 · 施工：T03

## 闭环

```
Decision + Beliefs + CriticalUncertainties
  → ResearchPlanner（按 impact 排序 top-k 生成 ResearchQuestion）
  → ResearchRun（SearchProvider + SearchAdapter → candidate evidence）
  → EvidenceDedupEngine（fingerprint / source family）
  → ClaimBindingEngine（绑定 / UNBOUND）
  → EvidencePolicy（scope / freshness / authority）
  → BeliefEngine（BeliefUpdateRecord + posterior_version++）
  → ResearchStopRule（8 类信号 → RESEARCH_MORE / SEARCH_EXHAUSTED / EXPERIMENT_REQUIRED）
```

## ResearchPlanner

确定性基线：`critical.impact` 降序取 top-k（`research_max_questions`）生成
ResearchQuestion；每个问题带 `search_queries` / `stop_condition` / 目标 claim。

## ResearchStopRule（8 类信号）

| 信号 | 含义 |
|---|---|
| marginal_value / belief_delta | 平均 \|Δp\| |
| duplicate_rate | dropped / retrieved |
| source_quality | 新证据平均 authority |
| source_diversity | 独立来源数 |
| claim_coverage | 目标 claim 覆盖 |
| search_cost | 查询数 |
| decision_change_prob | 概率变化（与翻转距离相关） |

判定：
1. `belief_delta < research_stop_marginal_value` 且 `duplicate_rate > research_stop_duplicate_rate`
   且轮次 > 1 → **SEARCH_EXHAUSTED**；
2. 最近一轮无新证据且仍有检索 → **EXPERIMENT_REQUIRED**；
3. 达到 `research_max_rounds` → **SEARCH_EXHAUSTED**；
4. 其余 → **RESEARCH_MORE**。

## 多轮去重

同一轮内精确 fingerprint 去重（drop，不持久化）；跨轮重复内容通过
"已持久化 evidence fingerprint 集合"过滤，避免同一信息被重复应用。
