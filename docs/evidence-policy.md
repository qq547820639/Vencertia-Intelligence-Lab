# Evidence Policy — 设计文档

> 算法等级标注：**[H1] 核心确定性规则** / **[H2] heuristic（可配置）** / **[H3] 占位**

## 1. 职责

Evidence Policy 是证据进入系统的**第一道确定性闸门**：

1. **赋权**：根据证据类型/来源给每条 Evidence 分配 `authority_level` 与有效权重。
2. **门控**：scope 合法性、Company Case 隔离、LLM 输出降权、验证状态。
3. **冲突管理**：标记 contradiction/conflict 状态。
4. **版本化**：authority 表本身可版本化（policy_version），供 Prediction Ledger 结算回溯。

## 2. Authority Hierarchy（初始策略，可版本化）

| 排序 | AuthorityLevel | 权重 | 说明 |
|---|---|---|---|
| 1 | `PROJECT_REALITY` | 1.00 | 项目一手现实（付款/合同/系统数据） |
| 2 | `PROJECT_DIRECT_BEHAVIOR` | 0.95 | 可观测项目行为（试用转化、使用日志） |
| 3 | `PROJECT_EXPERIMENT_RESULT` | 0.90 | 本项目实验结算结果 |
| 4 | `CUSTOMER_COMMITMENT_OR_PAYMENT` | 0.88 | 客户承诺/付款（弱于已发生付款，强于访谈） |
| 5 | `ELIGIBLE_EXTERNAL_CASE_FACT` | 0.75 | 通过 transferability 判定的外部案例事实 |
| 6 | `REVIEWED_EXTERNAL_RESEARCH` | 0.65 | 经审阅的外部研究（官方/一手研究） |
| 7 | `FOUNDER_STATEMENT` | 0.45 | 创始人陈述 |
| 8 | `LLM_INFERENCE` | 0.20 | 模型推断（有来源上下文，未验证） |
| 9 | `MODEL_PRIOR` | 0.10 | 无来源模型先验 |

> 该表继承 V10.2 Appendix A 证据强度规则（真实付款 > 合同/订单 > 真实客户行为 > 高质量访谈 > 可核验竞品交易 > 官方数据 > 可信行业数据 > 创始人/高管陈述 > 一般媒体 > 创业者判断 > Agent 推测），并映射为数值。

## 3. 映射规则（EvidenceType → AuthorityLevel）

| EvidenceType | 默认 AuthorityLevel | 条件 |
|---|---|---|
| REAL_PAYMENT | PROJECT_REALITY | scope=PROJECT/CUSTOMER |
| CONTRACT | PROJECT_REALITY | scope=PROJECT/CUSTOMER |
| OBSERVED_BEHAVIOR | PROJECT_DIRECT_BEHAVIOR | scope=PROJECT/CUSTOMER |
| EXPERIMENT_RESULT | PROJECT_EXPERIMENT_RESULT | 本项目实验 |
| CUSTOMER_COMMITMENT | CUSTOMER_COMMITMENT_OR_PAYMENT | scope=CUSTOMER |
| OFFICIAL_DATA | REVIEWED_EXTERNAL_RESEARCH | scope=MARKET/WORLD |
| PRIMARY_RESEARCH | REVIEWED_EXTERNAL_RESEARCH | scope=MARKET/CUSTOMER |
| REVIEWED_EXTERNAL_RESEARCH | REVIEWED_EXTERNAL_RESEARCH | — |
| ELIGIBLE_EXTERNAL_CASE_FACT | ELIGIBLE_EXTERNAL_CASE_FACT | 必须 transferability ≥ 阈值 |
| COMPANY_CASE_FACT | MODEL_PRIOR（项目侧不可用） | 未过 transferability：只能更新 WORLD/MARKET/BUSINESS_MODEL prior |
| FOUNDER_STATEMENT | FOUNDER_STATEMENT | scope=FOUNDER/PROJECT |
| EXPERT_INPUT | FOUNDER_STATEMENT ~ REVIEWED_EXTERNAL_RESEARCH 之间 | 按专家来源可靠度 |
| LLM_INFERENCE | LLM_INFERENCE | 有上下文、未验证 |
| MODEL_PRIOR | MODEL_PRIOR | 无来源 |
| SYSTEM_DERIVED | PROJECT_REALITY（系统计算） | 如财务指标计算 |

## 4. Scope Gate（重点）

### 4.1 Company Case Evidence ≠ Project Evidence

```text
COMPANY_CASE scope 的 Evidence 默认只能关联 scope ∈ {WORLD, MARKET, COMPANY_CASE} 的 Claim/Belief。
若希望它影响 PROJECT 的 WTP/需求信念，必须：
  1) 通过 transferability 判定（案例→项目关系属性，transferability ∈ [0,1]）；
  2) transferability ≥ 阈值（默认 0.6 [H2]）；
  3) 由人/评审确认（Policy: TRANSFERABILITY_REQUIRES_REVIEW [H1]）；
  4) 升级为 ELIGIBLE_EXTERNAL_CASE_FACT 后，按 0.75 权重进入项目 prior 更新
     （仅更新 prior，不直接作为项目证据计入伪计数）。
```

### 4.2 LLM Output ≠ Evidence

```text
LLM/能力模块输出在通过来源/可核验性校验前：
  - authority 强制降级为 MODEL_PRIOR 或 LLM_INFERENCE；
  - 不得标记 VERIFIED（除非有可追溯证据链）；
  - 不得直接写 Project State。
```

### 4.3 版本化

```text
authority 表 = AuthorityTable(version, rows[AuthorityLevel → weight], verification_multiplier, thresholds)
Policy 变化时 bump version；Belief 更新与 PredictionEntry 记录当时的 policy_version。
```

## 5. 接口签名

```python
@dataclass
class EvidenceGrade:
    evidence: Evidence
    authority_level: AuthorityLevel
    effective_weight: float
    scope_gate: str            # "OK" | "COMPANY_CASE_PRIOR_ONLY" | "REJECTED"
    reason: str

class EvidencePolicy:
    def grade(self, evidence: Evidence, policy: RuleSet | None = None) -> EvidenceGrade: ...
    def apply_authority(self, evidence: Evidence, policy_version: str) -> Evidence: ...  # 写回 authority_level
    def check_company_case_transferability(self, evidence: Evidence, project_context: dict) -> EvidenceGrade: ...
    def version(self) -> str: ...   # 当前 authority 表版本
```

## 6. 不变式

1. 任何 Evidence 入库前必须经过 `grade()`，authority_level 非空。
2. COMPANY_CASE 证据未经 transferability 判定不得影响项目 Belief。
3. LLM 输出不得自我声明 VERIFIED。
4. Evidence 不可变：修正 = 新记录 + SUPERSEDE（不覆盖原记录）。
