# Experiment Optimizer — 设计文档

> 算法等级标注：**[H1] 核心确定性算法** / **[H2] heuristic（可配置）** / **[H3] 占位**

## 1. 职责

在决策未收敛（ABSTAIN）时，从实验候选目录中选出**最值得执行的现实验证**，并给出排序与理由。

**核心原则（ADR-003）**：Decision Option Space 与 Information Acquisition Action Space **严格分离**：

- 决策选项 = 资源承诺（commit 6 weeks / stop / pivot / kill…）；
- 实验 = 信息获取行动（paid pilot / concierge MVP / 20 次访谈…）；
- 二者永不混在一个列表里打分；
- 未收敛时，系统必须**同时**输出 `INSUFFICIENT_EVIDENCE (ABSTAIN)` 与 `next_experiment`。

## 2. 评分公式

```text
priority_score(e) =
    EIG(e) × DecisionImpact(e) × Uncertainty(e) × ReversibilityBonus(e) × CriticalBoost(e)
    ─────────────────────────────────────────────────────────────────────────────
    cost(e) × time_penalty(e)
```

其中：

```text
Uncertainty(e)     = max(0.05, Σ_{b∈target_beliefs} uncertainty(b) × decision_weight(b))   [H2]
DecisionImpact(e)  = e.decision_impact（由决策引擎/用户提供，反映"改变决策的能力"）        [H2]
EIG(e)             = e.expected_information_gain（expected information gain，0~1）          [H2]
ReversibilityBonus = 0.5 + 0.5 × e.reversibility                                          [H2]
CriticalBoost      = 2.0 if e 命中 critical_belief else 1.0                                [H2]
time_penalty       = 1.0 + 0.15 × max(0, e.time − 1)   # 对数式时间惩罚，避免过度惩罚 2-3 天测试 [H2]
```

> 与 v0.1 公式一致（保留），仅将 `e.days` 重命名为 `e.time`，并显式要求 `decision_impact` 与 `expected_information_gain` 由输入提供（或由决策引擎计算）。

## 3. 输入输出

```python
@dataclass
class ExperimentProposalInput:
    decision: Decision                     # 含 relevant_belief_ids / critical_uncertainty_ids
    beliefs: list[Belief]
    critical_belief_id: str | None = None  # 来自 DecisionEngine
    candidates: list[Experiment]           # 实验候选目录（用户/模板/capability 提供）
    max_results: int = 5

@dataclass
class ExperimentProposalOutput:
    ranked: list[RankedExperiment]
    decision_insufficient: bool            # True 表示决策未收敛，必须同时输出实验
    reason: str
```

## 4. 接口签名

```python
class ExperimentOptimizer:
    def propose(self, inp: ExperimentProposalInput) -> ExperimentProposalOutput: ...
    def rank(self, experiments: list[Experiment], beliefs: list[Belief],
             critical_belief_id: str | None = None) -> list[RankedExperiment]: ...  # 兼容 v0.1
```

## 5. 与决策引擎的协作契约

```text
SolveOrchestrator:
  result = DecisionEngine.evaluate(...)
  if result.status == ABSTAIN:
      proposal = ExperimentOptimizer.propose(decision=..., beliefs=..., critical_belief_id=result.critical_belief_id, ...)
      # 输出同时包含 result（ABSTAIN）与 proposal.ranked[0]
```

## 6. 实验结算

实验运行后，结果经 OutcomeService 记录并转为 `EXPERIMENT_RESULT` 证据（authority=PROJECT_EXPERIMENT_RESULT），触发 Belief 更新 → Decision 再评估。

```python
class ExperimentService:
    def resolve(self, experiment_id: str, outcome: OutcomeType, result: str) -> ExperimentResolution:
        """更新 Experiment.status；生成 outcome_evidence；触发 belief update。"""
```

## 7. 不变式

1. 决策未收敛时，输出必须包含 ABSTAIN + next_experiment（不可只给一个）。
2. 实验候选评分必须显式含 cost/time 分母（防止"免费但耗时"实验被高估）。
3. 实验不得被当作决策选项参与 EU 打分。
4. 实验结算必须产生可审计的 Evidence（不得只改内存）。
