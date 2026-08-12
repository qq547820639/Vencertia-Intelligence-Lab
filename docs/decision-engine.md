# Decision Engine — 设计文档

> 算法等级标注：**[H1] 核心确定性算法** / **[H2] heuristic（可配置，默认值经验性）** / **[H3] 占位（留接口，不实现）**

## 1. 职责

给定 Objective、Decision（含 options）、当前 Belief 集合与 Policy（Invariant/Policy/Heuristic 三层），输出：

- 每个 option 的风险调整后效用（adjusted utility）
- 推荐选项（或 ABSTAIN）
- 决策置信度（confidence）
- 决策余量（decision margin）
- 决策类型（GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION/ABSTAIN）
- 决策关键不确定性（critical belief + 排序）
- 收敛状态（来自 ConvergenceEngine）

**边界**：Decision Engine **不**决定"该研究什么/该做什么实验"（那属于 ExperimentOptimizer）；**不**写入任何状态；纯函数式计算。

## 2. 输入

```python
@dataclass
class DecisionEngineInput:
    decision: Decision                    # options/relevant_belief_ids/horizon/reversible/estimated_cost
    beliefs: list[Belief]                 # 当前 Belief 集合（引擎只读）
    objective: Objective | None = None
    risk_aversion: float = 0.25           # [H2] 默认 0.25，可配置
    minimum_margin: float = 0.08          # [H2] 决策余量门槛，Policy 可覆盖
    max_critical_uncertainty: float = 0.45  # [H2] 关键不确定性门槛
    policy: RuleSet | None = None         # Invariant/Policy 生效
```

## 3. 算法（逐步）

### Step 1 — Expected Utility（每个 option）

```text
EU(o) = base_utility(o)
      + Σ_{belief b} coefficient(o, b) × P(b)        # P(b) = belief.probability
```

### Step 2 — Uncertainty Penalty

```text
U(o)    = Σ_b |coefficient(o, b)| × uncertainty(b)
penalty = risk_aversion × U(o) + irreversible_cost(o) + opportunity_cost(o)
```

- `irreversible_cost`：不可逆投入（沉没风险） [H2]
- `opportunity_cost`：做它放弃的最佳替代（由 OpportunityCostEngine 提供时使用；未提供时用 option 自带值） [H2]

### Step 3 — Adjusted Utility & 排序

```text
adjusted(o) = EU(o) − penalty(o)
按 adjusted 降序 → best, second
margin = adjusted(best) − adjusted(second)
```

### Step 4 — Decision-Critical Uncertainty（委托 UncertaintyEngine）

对每个 belief b 计算对"best vs second"的决策影响：

```text
impact(b) = |coefficient(best, b) − coefficient(second, b)| × uncertainty(b)
critical_belief = argmax_b impact(b)
critical_uncertainty = max impact(b)   （归一化到 [0,1]）
```

### Step 5 — 收敛判定与决策类型

```text
if margin < minimum_margin OR critical_uncertainty > max_critical_uncertainty:
    → status = ABSTAIN（convergence 由 ConvergenceEngine 细化）
    → recommended_option_id = None
else:
    → 按 option.kind / 语义规则映射决策类型：
        KILL 语义选项 → KILL
        PIVOT 语义选项 → PIVOT
        HOLD 语义选项 → HOLD
        CONDITIONAL_GO 语义选项 → CONDITIONAL_GO（条件列表来自 option.description）
        SELECT 语义选项 → SELECT_OPTION
        默认 → GO
```

**决策类型显式化规则**（与 V10.2 State Transition 对齐）：

| 来源语义 | 决策类型 | 说明 |
|---|---|---|
| 投入资源继续 | GO | 收敛且正期望 |
| 带条件继续 | CONDITIONAL_GO | 条件须列出并可验证 |
| 等待时机 | HOLD | 不投入，保持期权 |
| 换方向 | PIVOT | 前提失效但价值可迁移 |
| 停止 | KILL | 致命否定 |
| 多选项选择（非 go/kill） | SELECT_OPTION | 如选 A/B 渠道 |
| 证据不足 | ABSTAIN | 必须同时给 next_experiment |

### Step 6 — Confidence

```text
confidence = clip(0.5 + 0.35 × min(1, |margin|) − 0.35 × critical_uncertainty, 0, 1)   [H2]
```

---

## 4. 输出

```python
class DecisionEngineOutput(BaseModel):
    status: DecisionType
    recommended_option_id: str | None
    confidence: float
    decision_margin: float
    option_scores: list[OptionScore]
    critical_belief_id: str | None
    critical_uncertainty: float
    convergence_status: ConvergenceStatus
    rationale: list[str]
```

## 5. 接口签名

```python
class DecisionEngine:
    def evaluate(self, inp: DecisionEngineInput) -> DecisionEngineOutput: ...
```

## 6. 不变式

- 输出必须显式含 ABSTAIN（不得静默失败）。
- KILL 决策必须满足 Invariant：项目一旦 KILL 且被持久化，不能通过本引擎自动复活。
- 引擎不修改任何 Belief/Decision 对象（纯函数）。
- 决策类型与 Stage/Status 是三个独立维度（继承 V10.2 规则，不得合并）。

## 7. 与 v0.1 的关系

`decision.py` 的 `DecisionEngine.evaluate` 保留核心公式（EU + penalty + margin + abstain + confidence），升级点：

1. `DecisionStatus`（6 值）→ `DecisionType`（7 值，含 SELECT_OPTION）。
2. 增加 `convergence_status` 输出（与 ConvergenceEngine 协作）。
3. opportunity_cost 支持从 FounderOpportunityPortfolio 注入。
4. 决策类型显式映射（不再靠 option id 字符串包含 "kill"/"pivot" 推断）。
