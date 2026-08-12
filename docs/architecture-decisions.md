# Architecture Decision Records — ADR-001 ~ ADR-007

> 状态：Accepted（v1.0 设计基线）
> 格式：ADR（Context / Decision / Consequences）

---

## ADR-001 — Capability Modules：A0–A10 降级为 inference capability

**Context**：AgentV10.2 中 A0–A10 是"Agent"，拥有对话权威（Orchestrator 解释含义、State Transition 判定合法性、Routing 决定路由），多权威重叠导致状态漂移与 Prompt 膨胀。v0.1 已删除 "Agent" 作为域原语，但实现层仍可被理解为多 Agent。

**Decision**：A0–A10 在 v1.0 中统一为 `capabilities/` 下的 **inference capability modules**（LLM/Research/Retrieval/Financial/Market/Adversarial/CompanyCase/Statistical）。它们：
- 只接受 ContextBundle（读投影）与明确任务；
- 输出**候选**结构化对象（候选 Claim/Evidence/Decision 结构/实验候选）；
- 无 canonical truth authority；不得直接写 Project State；不得自宣 GO/KILL；
- 通过 `ModelProvider`/`SearchProvider` 等接口注入，可整体替换。

**Consequences**：能力可插拔、可独立 benchmark；多权威重叠消失；Prompt 从"指挥 Agent"变为"函数式任务描述"。代价：编译/研究类能力需要更强的 schema 约束与校验（EvidencePolicy 承担）。

---

## ADR-002 — Deterministic Runtime owns state mutation

**Context**：v0.1 中 `DecisionRuntime` 已在内存中确定性地变更 Belief；但事件日志、乐观锁、repository 边界缺失，能力模块仍可能绕过。V10.2 的 State Mutation Engine 概念只存在于 Prompt 中。

**Decision**：所有 Project State 变更必须经过 Deterministic Runtime 的单一入口（`SolveOrchestrator`/领域 Service），并满足：
1. 先 EvidencePolicy 校验，再写 Evidence；
2. Belief 更新只能由 BeliefEngine 触发（记录 update_method + 证据链）；
3. 每次变更写 Event Log（audit/replay，**不做** Event Sourcing——不重建状态，只留审计轨迹）；
4. Repository 层乐观锁（row_version）防 stale write；
5. 能力模块仅获得只读投影（ContextBundle）。

**Consequences**：状态可审计、可回放、可回归（L0 基准直接检验）；实现更重（事件+锁）。代价：任何新状态写入路径都要过 runtime 门，禁止快捷写。

---

## ADR-003 — Decision Option Space 与 Information Acquisition Action Space 严格分离

**Context**：v0.1 Iteration 1 曾把"低价实验"当决策选项，导致引擎把"先学"误判为"现在投入"。Iteration 2 已修复（IT LOG）。

**Decision**：v1.0 把两个空间在域模型中**物理分离**：
- `DecisionOption`（资源承诺：GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION）参与 EU 打分；
- `Experiment`（信息获取行动）由 `ExperimentOptimizer` 单独打分（EIG×DecisionImpact×Uncertainty÷Cost÷Time）；
- 决策未收敛时，输出**必须**同时包含 `ABSTAIN` 与 `next_experiment`（结构化答案两个字段，缺一不可）。

**Consequences**：用户不会把"再调研一周"误认为"投入三个月"；实验选择可独立基准（experiment selection accuracy）。代价：API/CLI 需要同时表达两类输出（SolveResult 结构承担）。

---

## ADR-004 — Company Case Evidence 与 Project Evidence 隔离（transferability gate）

**Context**：V10.2 的 Company Intelligence Runtime 已区分 Company Case 与 Project；但 V3 的 Transferability 是 Agent 派生输出，没有强制执行。若外部案例直接更新项目 WTP，将造成"别人验证过 ≠ 我的客户会付钱"的偏差。

**Decision**：
1. `CompanyCase` scope 的 Evidence 只能关联 `WORLD/MARKET/COMPANY_CASE` 的 Claim/Belief；
2. 要影响项目信念必须：(a) transferability 判定 ≥ 阈值(0.6)；(b) 需评审确认；(c) 升级为 `ELIGIBLE_EXTERNAL_CASE_FACT`（0.75）；
3. 即使通过，也只更新 WORLD/MARKET/BUSINESS_MODEL 的 **prior**，不直接作为项目伪计数；
4. `FundingRound` 永不作为需求证据（继承 V10.2 规则）。

**Consequences**：防止案例误用；Company Case 可安全批量导入。代价：transferability 判定需要人工/评审路径（Policy 配置）。

---

## ADR-005 — Framework-Agnostic：域不依赖任何具体模型/Agent 框架

**Context**：OSS_INTEGRATION_DECISIONS.md 已确立"adapter 边界"原则；LiteLLM/LangGraph/Qdrant 等均为准入候选。

**Decision**：域层与引擎层只依赖 `providers/` 接口（`ModelProvider`/`SearchProvider`/`RetrievalProvider`）：
- v1.0 实现：`MockProvider`（默认，离线可跑）+ `OpenAICompatibleProvider`（httpx，OpenAI 兼容端点）；
- 任何 OSS 集成（LiteLLM/LangGraph/Qdrant/DSPy/PyMC）都必须以 adapter 形式接入，并通过 benchmark 准入（ADR-006）；
- 事件与持久化接口同理：PostgreSQL 是 repository 实现之一，不是领域依赖。

**Consequences**：核心可在零外部依赖下运行/测试；换模型不改域逻辑。代价：能力模块的 prompt/schema 适配工作量前移。

---

## ADR-006 — Benchmark Precedes OSS Admission

**Context**：BENCHMARK_SPEC.md 与 IMPLEMENTATION_PLAN.md 已写入准入规则；v0.1 只做了 L0 合成回归。

**Decision**：任何新模型/OSS 集成进入生产前，必须通过冻结基准证明至少一项：
1. 统计可信的质量提升（无不可接受的成本/延迟）；
2. 同等质量下显著更便宜/更快；
3. 新必需能力且不降低关键指标。

v1.0 落地为三层基准：**L0**（合成策略回归，24 例起步）/ **L1**（历史 time-sliced，防泄漏：`leakage_audit_passed` 必须为 true，只能看到 T0 信息）/ **L2 展望**（prospective predictions 先登记后结算）。指标：decision accuracy、Brier、ECE、abstention quality、experiment selection accuracy、critical uncertainty accuracy、evidence precision-recall、decision regret。

**Consequences**：OSS 集成有客观闸门，防"架构靠感觉"；基准数据积累成为项目核心资产。代价：每个候选集成需要先写 harness + 跑基准（成本前置）。

---

## ADR-007 — Abstain 是一等输出，不是失败路径

**Context**：v0.1 已有 ABSTAIN（INSUFFICIENT_EVIDENCE）语义；v1.0 需把它提升为产品契约而非异常。

**Decision**：
- `ABSTAIN` 是 `DecisionType` 的正常成员，与 GO/KILL 并列；
- 每次 ABSTAIN 必须携带：critical_uncertainties 排序 + 推荐 next_experiment（或 SEARCH_EXHAUSTED 说明）；
- 收敛引擎显式区分 `RESEARCH_MORE`（还能低成本研究）与 `EXPERIMENT_REQUIRED`（必须现实实验）；
- benchmark 用 abstention quality（coverage × selective accuracy）度量，不允许"用覆盖率换正确率"作弊。

**Consequences**：系统在不确定时诚实拒答，符合产品立场；用户得到可执行的下一步而非废话。代价：收敛/实验推荐引擎成为必需组件（不能砍）。

---

## 附录：ADR 索引

| ADR | 主题 | 对应规格标题 |
|---|---|---|
| 001 | Capability modules | 核心原则 1（capability modules） |
| 002 | Deterministic state | 核心原则 1（deterministic runtime owns state mutation） |
| 003 | Decision-experiment 分离 | 规格 4（Decision Option Space 分离） |
| 004 | Company case 隔离 | 规格 5（Company Case Evidence ≠ Project Evidence） |
| 005 | Framework-agnostic | 规格 9（Model Gateway） |
| 006 | Benchmark precedes OSS | 规格 10（Benchmark 分层 + 准入） |
| 007 | Abstain 一等输出 | 规格 4（INSUFFICIENT_EVIDENCE + next experiment 同时输出） |
