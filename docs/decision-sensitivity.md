# Decision Sensitivity（v1.1）

> 版本：1.1 · 施工：T04

## 目的

回答两个问题：
1. **为什么是它** —— `DecisionTrace`：EU 分解（option utilities / belief
   contributions / penalties / margin / critical uncertainty）。
2. **什么会改变它** —— `DecisionSensitivity`：翻转阈值 + STRONG/FRAGILE 判定。

## DecisionSensitivityEngine

对每个 decision-relevant belief，以 `sensitivity_step`（默认 0.01）在 [0,1]
扫描 p，重算 `compute_option_scores`，找到最近一次推荐翻转：

```python
class FlipThreshold:
    belief_id: str
    claim_id: str
    current_value: float
    threshold_value: float
    would_become: str       # 翻转后的推荐 option id
    direction: str          # falls_below | rises_above
```

**Robustness**：
- `margin < robustness_margin_threshold`（0.05）或任一翻转阈值距当前值 < 0.10
  → `FRAGILE_DECISION`
- 否则 → `STRONG_DECISION`

`what_could_change_my_mind`：每条翻转生成一句可读说明。

## 输出示例（WTP 场景）

```
IF wtp falls_below to 0.28 (currently 0.42), recommendation becomes HOLD
IF wtp rises_above to 0.61 (currently 0.42), recommendation becomes GO
robustness: FRAGILE_DECISION
```

## 接线

- solve 后自动计算并持久化（`save_decision_sensitivity`），发
  `DECISION_SENSITIVITY_COMPUTED` 事件。
- API：`GET /v1/decisions/{id}/sensitivity`；CLI：`vencertia decision sensitivity`。
