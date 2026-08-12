# Belief Engine — 设计文档

> 算法等级标注：**[H1] 核心确定性算法** / **[H2] heuristic（可配置）** / **[H3] 占位（留接口）**

## 1. 职责

把 Evidence 对 Claim 的支持/反驳转化为 Belief 概率、不确定度与置信度的更新。**Belief 是派生状态**：每次更新必须记录 update_method、证据链与 prior/posterior。

## 2. 算法选择

| 方法 | 适用 | 等级 |
|---|---|---|
| **Beta-Bernoulli（默认）** | 二值命题；透明、可审计；v0.1 已实现 | [H1] |
| Weighted Log-Odds | 需要不对称权重/多证据合并；可替换 | [H2] heuristic Bayesian-like |
| PyMC 分层校准 | 数据充足后的模型级校准 | [H3] 占位（见 ADR-006，不默认引入） |

> 明确声明：这是 **heuristic Bayesian-like** 方法，不是严格贝叶斯推断。伪计数上限、折减系数均为可配置 heuristic，保证行为可解释、可回归。

## 3. 算法（Beta-Bernoulli 伪计数）

### Step 1 — Evidence 权重（来自 EvidencePolicy，见 evidence-policy.md）

```text
w(e) = authority_weight(e.authority_level)   # 9 级权威表
     × verification_multiplier(e.verification)
     × e.directness × e.reliability × e.relevance × e.strength
     × independence_discount(e.independence_group)
```

其中：

```text
authority_weight:
  PROJECT_REALITY 1.00 | PROJECT_DIRECT_BEHAVIOR 0.95 | PROJECT_EXPERIMENT_RESULT 0.90
  | CUSTOMER_COMMITMENT_OR_PAYMENT 0.88 | ELIGIBLE_EXTERNAL_CASE_FACT 0.75
  | REVIEWED_EXTERNAL_RESEARCH 0.65 | FOUNDER_STATEMENT 0.45
  | LLM_INFERENCE 0.20 | MODEL_PRIOR 0.10

verification_multiplier: VERIFIED 1.0 | ESTIMATED 0.75 | ASSUMED 0.35 | UNKNOWN 0.20

independence_discount(e): 同 independence_group 第 n 条 → 1/(1+n−1)   [H2]
```

### Step 2 — 伪计数更新

```text
mass = max_pseudo_observations × w(e)          # max_pseudo_observations = 3.0 [H2]
if direction == SUPPORTS:    alpha += mass
elif direction == CONTRADICTS: beta += mass
else (NEUTRAL):              alpha += 0.15×mass; beta += 0.15×mass
```

### Step 3 — 概率 / 不确定度 / 置信度

```text
probability = alpha / (alpha + beta)

evidence_mass = alpha + beta − 2
variance = 4 × probability × (1 − probability)
maturity = 1 / (1 + evidence_mass/6)
uncertainty = clip(variance × (0.35 + 0.65 × maturity), 0, 1)    [H2]

confidence = 1 − uncertainty
```

### Step 4 — 支持/反对证据清单

```text
supporting_evidence_ids   = [e.id for e in applied if direction == SUPPORTS]
contradicting_evidence_ids = [e.id for e in applied if direction == CONTRADICTS]
```

### Step 5 — Conflict 检测

若同 claim 的支持与反驳证据同时存在且双方有效权重均 ≥ 阈值，标记 `conflict_status=CONFLICTED`（必须显式呈现，不得静默平均） [H2]

## 4. 输入输出

```python
@dataclass
class BeliefUpdateInput:
    beliefs: list[Belief]
    evidence: list[Evidence]          # 已通过 EvidencePolicy 校验并赋 authority
    update_method: UpdateMethod = UpdateMethod.BETA_BERNOULLI

@dataclass
class BeliefUpdateOutput:
    beliefs: list[Belief]
    applications: list[EvidenceApplication]   # {evidence_id, belief_id, effective_weight, alpha_delta, beta_delta, dedup_discount}
    conflicts: list[ConflictAlert]            # {claim_id, evidence_ids, reason}
```

## 5. 接口签名

```python
class BeliefEngine:
    def update(self, inp: BeliefUpdateInput) -> BeliefUpdateOutput: ...
    def uncertainty_of(self, belief: Belief) -> float: ...   # 供其他引擎复用
    def prior_of(self, belief: Belief) -> float: ...         # 返回当前 prior
```

## 6. 不变式

- 每条 Evidence 至多贡献 `max_pseudo_observations` 个伪观测（防止单条强证据垄断）。
- 重复/相关证据必须折减（independence_group）。
- 无来源模型输出只允许 `MODEL_PRIOR/LLM_INFERENCE` 权重进入。
- Company Case 证据在未通过 transferability 判定前**不得**进入项目 Belief（scope gate，见 evidence-policy.md）。

## 7. 与 v0.1 的关系

`evidence.py` 的 `EvidenceEngine.apply` 保留（权重公式 + 相关性折减 + 伪计数），升级点：

1. SOURCE_PRIOR（10 类 SourceType）→ AuthorityHierarchy（9 级 AuthorityLevel，可版本化）。
2. 拆分为 EvidencePolicy（赋权/门控）与 BeliefEngine（更新）两个职责。
3. 增加 conflict 检测与 `update_method` 记录。
4. claim_ids 多对多支持。
