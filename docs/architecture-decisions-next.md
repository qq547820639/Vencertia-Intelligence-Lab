# Architecture Decision Records — ADR-008 ~ ADR-012（v1.1 增量）

> 状态：Accepted（v1.1 设计基线）
> 上游：ADR-001 ~ ADR-007（v1.0，原样保留，不推翻）
> 作者：高见远（首席架构师）
> 格式：ADR（Context / Decision / Consequences）

---

## ADR-008 — Research evidence must bind to claims

**Context**：v1.0 的 `SolveOrchestrator._research()`（`runtime/runtime.py` 587 行附近）为检索/搜索产生的 Evidence 写入 `claim_ids=[]`，这些证据虽然入库，却从未关联任何 Claim，因此永远不会进入 BeliefEngine 的证据链。结果：研究证据与判断闭环"物理断裂"，且没有任何记录能评估"研究证据到底绑得对不对"（无法计算 Claim Binding Accuracy）。

**Decision**：所有进入系统的研究证据必须经过 **Claim Binding Pipeline**：
1. Research Result → `ClaimExtractor` 提取候选 Claim；
2. `ClaimMatcher` 匹配既有 Claim：`EXISTING_MATCH`（可多条，`MULTIPLE_MATCH`）或 `NO_MATCH`；
3. `NO_MATCH` 的候选 Claim 必须通过 **deterministic validation** 才能成为 `CandidateClaim`（`validation_status=PENDING`），**不得**直接 canonical 为 `Claim`；
4. `EvidenceClaimLinker` 产出 `EvidenceClaimBinding`：BOUND（可一证多绑）或显式 `UNBOUND_EVIDENCE`（claim_id=None，**不偷偷绑定**，允许重处理）；
5. 绑定记录持久化：`evidence_id/claim_id/binding_confidence/binding_method/model/provider/matched_at`。

**Consequences**：
- 证据→Claim→Belief 链可追溯；研究证据真正影响判断；
- `UNBOUND_EVIDENCE` 成为显式库存（可重处理、可审计），消除"静默丢弃/静默空绑"；
- Claim Binding Accuracy 有了唯一数据源（L1 指标）；
- 代价：绑定流水线是 solve 必经步骤（计算成本前置），但确定性实现可离线回归。

---

## ADR-009 — Provider configuration belongs in composition root

**Context**：v1.0 的 `Settings.model_provider` 已存在，但 `api.py` 的 `default_runtime()` 与 `cli.py` 的 `_default_runtime()` **各自硬编码** `MockProvider/MockSearchProvider/MockRetrievalProvider`。换 Provider 需要改两处代码；`MODEL_PROVIDER=openai_compatible` 根本不生效。未来接入 LiteLLM/Anthropic/Gemini/Local（ADR-006 准入）时，这种双装配会扩散。

**Decision**：引入单一 **Composition Root**：
- `providers/factory.py`：`create_model_provider/search/retrieval/bundle(settings)` + `register_model_provider(name, factory)` 注册表；
- `container.py`：`ApplicationContainer`，装配链固定为 `Settings → Repository Factory → Provider Factory → EngineBundle → SolveOrchestrator → FastAPI/typer`；
- `api.py` 与 `cli.py` **共用** `build_container()`，不维护第二套 wiring；
- 未来 provider 通过注册表追加，调用方零改动。

**Consequences**：
- Provider 由环境变量真实决定（`MODEL_PROVIDER=mock|openai_compatible`）；
- 单一装配可整体单测（`test_container.py`）；
- OSS provider 准入后只需 `register_model_provider` + benchmark 证明（ADR-006）；
- 代价：装配逻辑集中到一个文件，任何依赖注入调整都在 container 内完成。

---

## ADR-010 — Context is decision-relevant, not generic memory retrieval

**Context**：v1.0 的 `ContextBuilder` 按"authority 权重 + recency"返回 top-N evidence，beliefs 按插入顺序截断。这与当前要编译/要研究的决策**无关**：一条权威但无关的旧证据会排在决策关键证据前面，研究规划与能力推理拿到的上下文质量不可控。

**Decision**：`/solve` 中每次 Decision Compiler / Research Planner / Capability 推理前，用 **`DecisionRelevantContextBuilder`** 构造统一 `ContextBundleV11`：
- 组合 15 类上下文：Founder / Project / Objectives / Claims / Beliefs / Strong Evidence / Contradictory Evidence / Recent Outcomes / Open Experiments / Previous Decisions / Company Cases / Financial / Constraints / Conflict Alerts / Critical Uncertainties；
- 排序维度（settings `context_rank_weights` 可配）：scope match / decision relevance / belief dependency / authority / evidence strength / temporal validity / recency / conflict / semantic / information value；
- v1.1 不要求向量库：默认 deterministic/lexical 排序；`SemanticRanker` 为可替换 adapter（未来 Qdrant 等按 ADR-006 接入）。

**Consequences**：
- 上下文与决策目标对齐，编译/规划质量可复现、可回归；
- deterministic 基线使 L0 可测"相关性排序正确性"；
- 代价：builder 需要读取更多数据源（15 类），读取路径有成本；排序权重需 benchmark 调参。

---

## ADR-011 — Research requires an explicit stopping rule

**Context**：v1.0 的收敛引擎有 `RESEARCH_MORE / SEARCH_EXHAUSTED / EXPERIMENT_REQUIRED` 三态，但没有基于信号的评估——`SEARCH_EXHAUSTED` 只是"没有便宜实验时的兜底"。实际 solve 中研究可能无限循环或任意停止，"再调研一下"没有终止标准。

**Decision**：引入 **`ResearchStopRule`**，每个研究轮次后按 8 类信号评估并输出 `ResearchStopReport`：
- marginal evidence value（新证据边际价值）、source diversity、claim coverage、belief uncertainty delta、probability decision change（结合 DecisionSensitivity 翻转距离）、search cost、duplicate rate、source quality；
- 判定：
  1. 连续 duplicate / 低 authority / 同 source family / belief delta 低于阈值 → `SEARCH_EXHAUSTED`；
  2. 剩余关键不确定性只能由现实观测解决 → `REAL_WORLD_EXPERIMENT_REQUIRED`（`EXPERIMENT_REQUIRED`）；
  3. 否则 `RESEARCH_MORE`（受 `research_max_rounds` 上限约束）。

**Consequences**：
- 研究循环有界、可解释（每条停止都有信号依据）；
- `SEARCH_EXHAUSTED` 从"兜底"变为"诚实声明：桌面研究到头了"；
- 与 ExperimentOptimizer 衔接：停止研究后必须给出可执行实验或"残余不确定性下决策"；
- 代价：需要每轮统计信号（额外计算）；信号阈值需 L0/L1 校准。

---

## ADR-012 — External intelligence cannot directly mutate canonical state（v1.1 hardening）

**Context**：ADR-002 已确立"Deterministic Runtime owns state mutation"，但 v1.0 研究路径存在缺口：搜索候选证据**直接持久化**（`claim_ids=[]`），Provider 故障（timeout/rate limit/invalid JSON/schema mismatch/unavailable/empty/partial）也没有统一的失败分类，异常 JSON 可能污染实体存储。v1.1 加入绑定、提取、规划等更多外部智能输出后，缺口会放大。

**Decision**：外部智能（LLM/搜索/研究/案例）的任何输出遵循纪律：**Candidate → Validation → Only then persistence**：
1. Provider 层：`with_resilience` 统一捕获并分类失败（Timeout / RateLimit / InvalidJSON / SchemaMismatch / Unavailable / Empty / Partial），重试后返回结构化错误；
2. 业务层：候选 Claim 过 deterministic validation；候选 Evidence 过 Claim Binding + EvidencePolicy（scope/freshness/authority）；候选实验过 `ExperimentOptimizer.validate`（criteria 强制）；
3. 任何失败/未通过校验的输出**不得**写入 canonical 实体（可写 `UNBOUND_EVIDENCE`/`ProviderCallRecord` 等审计型记录，不污染判断状态）。

**Consequences**：
- canonical 状态不可能被外部智能污染（含故障路径）；
- 失败可观测（call records + 结构化错误）可重试；
- 代价：所有外部入口多一道校验闸门；ProviderCallRecord 需要明确"不记 prompt"红线（敏感内容零落库）。

---

## ADR-013 — Research Evidence and Project Outcome Evidence Have Different Authority（v1.1.1）

**Context**：v1.1 的 EvidencePolicy 已有 authority 层级（`PROJECT_REALITY`
权重最高），但文档与实现未把"**外部研究证据**"与"**本项目结果证据**"的
权威性差异讲透，导致集成方容易把二手研究当成本项目事实。GAP-08 明确该纪律。

**Decision**：外部研究证据与本项目结果证据**权威性不同**，且这种差异是
**结构性**的，不是打分参数可抹平的：

- **Secondary research** 估计的是**外部现实**（市场容量、竞品、行业增速）——
  它是关于"世界其他地方"的估计；
- **Company cases** 提供的是**可迁移先验**（另一家公司发生了什么，可迁移到
  本公司的力度受 transferability gate 约束，ADR-004）；
- **Founder statements** 是**报告性信息**（创始人声称什么，不是直接行为）；
- **Project experiments** 观察的是**本项目自己的世界**（本项目的客户、
  本项目的转化、本项目的成本）；
- **Customer payment** 是**直接行为证据**（客户真实付钱，最接近本项目现实）。

因此项目结果证据（project experiments / direct customer payment /
observed behavior inside this venture）携带**根本不同**的权威等级：
**External research cannot directly produce PROJECT_REALITY authority.**
外部研究最多被提升到 `REVIEWED_EXTERNAL_RESEARCH` / `ELIGIBLE_EXTERNAL_CASE_FACT`，
永远不能因为"很多来源都这么说"而自动变成本项目的 `PROJECT_REALITY`。
要获得 `PROJECT_REALITY`，必须有本项目内的直接观察/实验/支付行为。

**Consequences**：
- 决策引擎不会把"行业报告说 80% 客户愿意付"直接当作"本 ICP 会付"；
- 公司案例只能作为先验（transferable prior），不能直接替代本项目实验；
- 需要在 `docs/evidence-policy.md`、API 文档与示例中把该差异讲清楚；
- 代价：外部研究在信念更新中的权重被结构性压低，必须靠项目内实验补足。

---

## 附录：ADR 索引（v1.0 + v1.1）

| ADR | 主题 | 版本 |
|---|---|---|
| 001 | Capability modules（A0–A10 降级为 inference） | v1.0 |
| 002 | Deterministic runtime owns state mutation | v1.0 |
| 003 | Decision/Experiment 空间分离 | v1.0 |
| 004 | Company Case 证据隔离（transferability gate） | v1.0 |
| 005 | Framework-agnostic（adapter 边界） | v1.0 |
| 006 | Benchmark precedes OSS admission | v1.0 |
| 007 | Abstain 是一等输出 | v1.0 |
| 008 | **Research evidence must bind to claims** | v1.1 |
| 009 | **Provider config belongs in composition root** | v1.1 |
| 010 | **Context is decision-relevant, not generic memory retrieval** | v1.1 |
| 011 | **Research requires an explicit stopping rule** | v1.1 |
| 012 | **External intelligence cannot directly mutate canonical state** | v1.1 |
| 013 | **Research Evidence and Project Outcome Evidence Have Different Authority** | v1.1.1 |
