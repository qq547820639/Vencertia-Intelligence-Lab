# Calibration Engine — 设计文档

> 算法等级标注：**[H1] 核心确定性算法** / **[H2] heuristic（可配置）** / **[H3] 占位**

## 1. 职责

度量"系统说 70% 的时候，现实是否真的 70% 发生"。校准是 Vencertia 持续变聪明的核心机制：

1. 计算 Brier Score（整体概率质量）；
2. 计算 Expected Calibration Error（ECE，分桶校准误差）；
3. 分桶明细（confidence/empirical rate/gap）；
4. **分层**：ALL / MODEL（model_tag）/ DOMAIN（领域）/ MODULE（引擎模块）；
5. 输出可解释的校准报告，供人类复盘。

## 2. 指标定义

```text
Brier = (1/n) × Σ (p_i − o_i)²            # o_i ∈ {0,1}

ECE = Σ_{bucket k} (n_k/n) × |conf_k − rate_k|
      conf_k = mean(p in bucket)
      rate_k = mean(o in bucket)

分桶：默认 10 桶 [H2]，按概率 [0,1] 等宽切分。
```

## 3. 分层范围

| 层级 | 分组键 | 用途 |
|---|---|---|
| 模块级 | engine/module（decision/evidence/belief） | 定位引擎偏差 |
| 模型级 | model_tag × policy_version | 评估 LLM 能力模块校准 |
| 领域级 | domain（b2b-saas/consumer/fintech…） | 领域差异 |
| 全局 | ALL | 总体健康度 |

## 4. 输入输出

```python
@dataclass
class CalibrationInput:
    predictions: list[PredictionEntry]   # 已结算（resolution != OPEN）
    scope: CalibrationScope = CalibrationScope.ALL
    scope_key: str = "ALL"
    bins: int = 10

class CalibrationEngine:
    def report(self, inp: CalibrationInput) -> CalibrationProfile: ...
    def update(self, inp: CalibrationInput) -> CalibrationProfile: ...   # 触发 CALIBRATION_UPDATED 事件
    def update_all_scopes(self, predictions: list[PredictionEntry]) -> list[CalibrationProfile]: ...
```

## 5. 校准使用策略（不自动改概率）

v1.0 **不**自动把 Belief 概率按校准曲线重标定（避免循环依赖与不可解释性）；只输出报告与建议。模型级校准重标定列为 [H3]（数据充足后按 ADR-006 准入）。

## 6. 与 v0.1 的关系

`calibration.py` 的 `CalibrationEngine.report` 保留（Brier/ECE/buckets），升级点：

1. `PredictionRecord` → `PredictionEntry`（含 belief_snapshot/context_snapshot_hash/policy_version）。
2. 新增分层 scope（MODEL/DOMAIN/MODULE）。
3. 触发 `CALIBRATION_UPDATED` 事件。

## 7. 不变式

1. 只统计已结算预测；OPEN 不计入。
2. 结算不可逆：PredictionEntry 一旦 resolve 不得改写 original probability（防事后篡改）。
3. 快照哈希校验失败必须告警（表示上下文被篡改）。
