# AgentV11 Prompt 架构包审查 + v1.1.2 代码完整映射

> 审查人：高见远（Architect）· 日期：2026-08-13
> 性质：纯审查，不改源码、不写实现代码。所有论断标注文件路径/行号/符号。
> 范围：`legacy/agent_v11/_extracted_txt/`（34 文件 / 21196 行）↔ `src/vencertia/`（92 py）
> 上游参考：`docs/v1.1.2-code-walkthrough-review.md`（上一轮全仓库走读，含模块地图 + 3 GAP + 5 P0）

---

## 0. 执行摘要

AgentV11 是一份**概念成熟度很高、但工程落地度为零**的下一代 Prompt 架构蓝图。它把 V10.2 的"每个 Agent 各带一整套全局规则"重构为 7 层 Prompt Stack，并把三个隐含的模型科学问题正式化：**参数来源治理（provenance/status）、概率语义（calibration_status）、依赖与 double-counting（BeliefEdge/shared_signal）**，同时引入 Stakes-aware Adaptive ABSTAIN、Model Critic、Decision Validation（Forecast Calibration 与 Decision Performance/Regret 分离）等概念。

对照 v1.1.2 代码，结论可概括为一句话：**V11 的"确定性 Runtime Policy"层，v1.1.2 已经用代码实现了一大半（dedup/belief update/EU/abstain/calibration/prediction ledger）；V11 真正的新增量，几乎全部落在"给现有数字加上来源、状态、关系和可追溯语义"这一层**——而这一层恰是 v1.1.2 目前最薄弱的"语义标注"空白。

关键映射结论（详见 B 节逐项）：

- ✅ **已实现（6 项部分）**：证据 dedup/防 double counting（evidence 级）、Brier/ECE 校准、Prediction Ledger 快照、ABSTAIN（单一全局阈值）、机会成本、7 态收敛、5 段输出素材（SolveResultV11 已含全部字段）。
- 🟡 **部分实现（8 项）**：calibration_status（只有 2 态）、Utility（纯线性 EU）、VOI（有 decision_impact 代理但无 action-change/option value）、Sequential Decision（无 WAIT/STAGE 选项）、Regret（只在 benchmark 指标，无决策级 ledger）、模式/输出合同（无 EXPLORE/OPERATE、无 Progressive Disclosure）。
- ❌ **完全缺失（4 项）**：DecisionModelSpec + 参数 provenance、BeliefEdge/因果图、StakesProfile/Adaptive ABSTAIN、Model Critic。

V11 与 v1.1.2 的哲学**天然同源而非冲突**：V11 的核心主张"LLM proposes; schema constrains; runtime governs; ledgers preserve history"正是 v1.1.2 三层架构（Repository 唯一写入口 + 确定性引擎 + Capability 无写权）的书面化。真正需要裁决的是**版本策略**——V11 自己的回归报告已给出答案：*"further broad prompt rewriting has diminishing return; the next quality jump comes from executable schemas, deterministic services, mutation permissions and automated regression"*（Full System Prompt Regression Report §7）。即：**不要继续 prompt 文档驱动，应走"蓝图 → Pydantic Schema → 确定性服务 → 回归夹具"的施工图路线**（与 v1.1.x 完全一致）。

---

## A. V11 包内容盘点与质量评估

### A.1 文件清单分类

| 类别 | 文件（提取 txt，34 个） | 行数 | 定位 |
|---|---|---|---|
| **主蓝图（最权威）** | `Vencertia_V11_Prompt_Architecture_修改蓝图V2.txt` | 519 | 总设计（版本标 "Blueprint v1.0"） |
| **Schema** | `V11 prompt__...V11_Schema_Specification_v0.2.txt` | 3084 | Pydantic/JSON Schema 契约（19 对象 + 18 枚举） |
| **共享核心协议** | `V11 prompt__规范文件V11 V0.1__...V11_Core_Protocol_Pack_v0.1.txt` | 813 | 15 条 Global Invariants + 10 个 Protocol |
| **核心补丁** | `V11 prompt__...V11_Core_v0.2_Patch.txt` | 250 | P-01~P-06 六处规范性修补 |
| **v0.2 Agent 规范（控制面）** | Orchestrator / Routing / Model Critic / Next Action Planner / Memory Write（各 v0.2） | ~14k | 核心闭环 Prompt |
| **v0.1 Agent 规范（控制面旧版）** | 同前缀 `规范文件V11 V0.1__`（Orchestrator/Routing/Model Critic/Next Action Planner/Memory Write v0.1） | ~12k | 被 v0.2 覆盖 |
| **State Transition** | `V11 prompt__...State_Transition_V11_v0.1.txt` | 约 33k(原文) | **唯一未升 v0.2 的控制面组件** |
| **Specialist（业务面）** | Business Plan Architect / Execution Strategy / Financial / Founder Diagnosis / Founder Matchmaking / Market Opportunity / Startup Case Intelligence / Venture Design（均 v0.1） | ~12k | 8 个业务专家 |
| **Runtime Policy** | Stakes_Reversibility / Utility / Evidence_Aggregation_Belief_Update（均 v0.1） | ~2.7k | 三个确定性策略 |
| **回归报告** | Full_System_Prompt_Integrated_Regression_Report_v0.1（40 例）/ Core_Integrated_Contract_Regression_Report_v0.2 / Core_Integrated_Regression_Test_v0.2 / Specialists_Batch1、Batch2 报告 v0.1 | ~4.4k | **规范级模拟，非可执行测试** |
| **重复版本/测试文件** | `V11 prompt__测试文件__...` 前缀 3 个（Core Regression Test v0.1/v0.2 + Report v0.1）、`_extracted_txt/full_pack/`（22 文件，含 MANIFEST.txt） | ~3k | 与上面大量重复 |

### A.2 版本演进 v0.1 → v0.2（抽查 diff 要点）

抽查 `Core Protocol Pack v0.1` ↔ `Core v0.2 Patch`、`Orchestrator v0.1` ↔ `v0.2` 两对，v0.2 是**增量修补而非推倒重写**：

| Patch 编号 | v0.1 的问题 | v0.2 的裁决 |
|---|---|---|
| P-01 | `LifecycleMode` 同时表达"公司阶段"和"当前决策阶段" | 拆成 `VentureMode(EXPLORE/OPERATE) × DecisionPhase(DISCOVER/VALIDATE/COMMIT/EXECUTE/REVIEW)` 双正交轴 |
| P-02 | "recent ModelCritique" 无 freshness 语义 | 加 `CritiqueValidity` + `invalidation_triggers` + `external_fact_cutoff` |
| P-03 | A4(Critic) 到 A7(Next Action) 靠 prose 交接 | 加结构化 `CritiqueResolutionTarget` |
| P-04 | 回归只约束 TEST/HOLD，漏 WAIT | 统一 TEST/HOLD/WAIT 的 exit/change/deadline/fallback 合同 |
| P-05 | 官方来源也可能过期/冲突 | 加 `External Fact Freshness & Source Conflict Protocol` |
| P-06 | Evidence promotion 批准者抽象 | 冻结 `Evidence Review & Promotion Service Contract`（LLM/Connector 无批准权） |

### A.3 文档族内部一致性抽查

| 抽查项 | 结果 | 判定 |
|---|---|---|
| Schema v0.2 对象字段 vs 主蓝图 §4 对象清单 | 蓝图列 13 对象；Schema v0.2 展开为 19 对象 + 18 枚举。蓝图 `EvidenceObservation`→Schema `EvidenceRecord/ObservationRecord`（拆了晋级链）；蓝图 `DecisionRecord`→Schema `DecisionRecord + DecisionRecommendation + DecisionLedgerEntry`；蓝图 `OutcomeRecord`→Schema `OutcomeRecord + ForecastCalibrationRecord + DecisionPerformanceRecord`。**方向一致，Schema 更细** | ✅ 对齐 |
| Schema v0.2 枚举 vs Core Protocol Pack v0.1 附录 A 语义词表 | 逐项对应（ProvenanceType/CalibrationStatus/GovernanceStatus/BeliefRelationType/UtilityRelationType/ActionState/StakesClass/CounterfactualStatus/CritiqueFindingType） | ✅ 对齐 |
| Core Patch v0.2 vs Schema v0.2 | Schema §3 已含 VentureMode/DecisionPhase/CritiqueValidity 等 P-01/P-02 新枚举 | ✅ 对齐 |
| 状态词：主蓝图 §5.2 vs Core Protocol §8.3 vs Schema §3 | **蓝图写 ACT/EXPERIMENT/WAIT/HOLD/PIVOT/KILL；Core+Schema 写 ACT/TEST/HOLD/WAIT/STOP，并把 PIVOT/KILL 移出 ActionState 归入 option 语义。`EXPERIMENT` 在 v0.2 被改名为 `TEST`** | ⚠️ 演进改名（未冲突，但需注意蓝图非最终权威） |
| State Transition v0.1 vs Core v0.2 双轴 | State Transition 仍为 v0.1（`mode_projection` 单轴），未更新到 VentureMode×DecisionPhase | ⚠️ 版本滞后 |
| 回归报告声称的测试 vs "测试文件"目录 | Full System Prompt Report 称 40/40 PASS，但 §0 明确"**specification-level integration simulation；does not execute production Pydantic validators/databases**"。`测试文件__Core_Integrated_Regression_Test_v0.2` 是**提示词级语义场景清单（R01-R40/C01-C12），不是可执行代码测试** | ✅ 诚实（无伪造，但"测试"是文案不是代码） |

### A.4 质量评价

**成熟度：概念层 9/10，工程层 2/10。**

- **强项**：单一权威来源纪律、provenance/status 治理、"未校准分数不得冒充概率"、double-counting guard、Adaptive ABSTAIN 退出合同、Model Critic、Forecast vs Decision Performance 分离、counterfactual honesty——这些是决策科学上很扎实的语义设计，且**每一处都诚实标注了"留给 Runtime/Schema 的开放项"**（Core Protocol §15.1、Schema §0.2、Runtime Policy §0）。
- **可操作性**：Schema v0.2 给出了 `schemas_v11/` 参考目录布局（base/enums/value_types/context/evidence/belief/model_spec/utility/stakes/experiment/critic/decision/outcome/calibration/agent_io/compatibility/schema_version，共 16 文件），可直接照搬落地。
- **自身问题**：
  1. **四层版本号混乱**：主蓝图标 "v1.0"、Schema v0.2、Core Protocol v0.1、Core Patch v0.2、Runtime Policy v0.1，且 "Blueprint v1.0" 实际是比 "Schema v0.2" 更早的总设计——版本空间无单调全序，容易误判权威。
  2. **状态词漂移**：`EXPERIMENT→TEST`、`PIVOT/KILL` 进出 ActionState（A.3），若直接照蓝图 §5.2 落地会与 Schema v0.2 冲突。
  3. **冗余**：`full_pack/` 22 文件与 `测试文件__` 前缀 3 文件是重复版本（Core Regression Test v0.1/v0.2 字节数同为 10382，近乎同内容）。
  4. **State Transition 未同步 v0.2 双轴**，是唯一停在 v0.1 的控制面组件。

---

## B. V11 蓝图 → v1.1.2 代码映射表（核心交付物，12 项）

判定符号：✅已实现 / 🟡部分实现 / ❌缺失（N/A=代码侧无对应物）

### B.1 DecisionModelSpec + parameter provenance —— ❌ 缺失

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| 每个重大决策先有 `DecisionModelSpec`（decision_id/model_version/objective/constraint/option/belief/edge/utility/threshold/parameter_provenance/approved_by） | **无 DecisionModelSpec 对象**。最接近的是 `Decision`（`domain/decision.py:31-51`），有 id/objective_id/options/horizon/reversible/estimated_cost，但**无 model_version、无 provenance、无 assumptions、无 approved_by** | ❌ |
| 每个 coefficient/threshold/gate 标来源 `USER_DEFINED/OBSERVED/DOMAIN_DEFAULT/EMPIRICALLY_ESTIMATED/LLM_PROPOSED/UNKNOWN` | **无 parameter provenance 枚举**。仅有 `Evidence.Provenance`（`domain/evidence.py:21-26`：source_id/source_url/tool/actor/raw_extract）是"证据来源元数据"，非"参数来源"。`Objective.source="user|system|capability"`（`domain/objective.py:30`）是三值字符串，非六态 provenance | ❌ |
| LLM_PROPOSED 不得静默 APPROVED | 代码侧 LLM 产物（`DecisionCompiler`，`capabilities/__init__.py:55-100`）直接 `model_validate` 成 `Objective/Decision/Belief`，**无 PROPOSED/APPROVED 状态门**，LLM 建议的参数直接进入确定性引擎 | ❌ |

**对应物**：`config.py` 的阈值（`minimum_margin=0.08`/`max_critical_uncertainty=0.45`，`config.py:90-91`）是"versioned policy default"的雏形（对应 G-14），但**未挂 provenance/status 标签，也未按 domain/stakes 分层**。

### B.2 calibration_status 语义 —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| 5 态 `UNCALIBRATED/LOW_SAMPLE/DOMAIN_CALIBRATED/USER_CALIBRATED/VALIDATED` | `CalibratedConfidence.status` 只有 **2 态 `UNCALIBRATED|CALIBRATED`**（`domain/calibration.py:42`）。`calibration_engine.py:174-214` 的 `calibrate()` 当 `n < min_samples(=20)` 返回 UNCALIBRATED，否则 CALIBRATED | 🟡（缺 4 态粒度） |
| 每个概率字段必须带 calibration_status | `Belief` **无 calibration_status 字段**，只有 `calibration_group`（`domain/belief.py:57`）；`Decision.confidence`、`OptionScore` 均无状态标注。`confidence_calibrator.py` 有校准逻辑但结果未回写 Belief/Decision | 🟡 |
| 未经校准 0.73 不得展示为"73% 真实概率" | 代码侧 `belief.probability`/`decision_result.confidence` 直接是小数，**无 EstimateType（ORDINAL_SUPPORT/MODEL_SCORE/CALIBRATED_PROBABILITY）区分** | ❌ |

**对应物**：`calibration_engine.py:216-252` 的 `_bins/_map_piecewise`（分桶+分段映射）与 `confidence_calibrator.py:56-94` 是**两套重复实现**（上一轮报告 §5.7 已指出 DRY 违例），正好是 V11 "Forecast Calibration" 的数值内核，但缺 `EstimateType` 语义层。

### B.3 BeliefEdge / 因果图 / 防 double counting —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| `BeliefEdge`（CAUSES/DEPENDS_ON/MEDIATES/SHARES_LATENT_FACTOR/SHARED_SIGNAL/REDUNDANT_WITH/MUTUALLY_EXCLUSIVE/UNKNOWN_RELATIONSHIP） | **无 BeliefEdge 对象、无因果图**。全库 grep 无 `BeliefEdge/CAUSES/DEPENDS_ON/shared_signal_group/shared_latent` | ❌ |
| 同一付款支持 Problem/WTP/Demand 须记 shared_signal_group 防三次独立计权 | **evidence 级有近似**：`evidence_dedup.py:75-142` 用 `content_fingerprint` + `source_family` + `independence_group` 分组；`belief_engine.py:177-183` 在同 `independence_group` 内做 `discount = 1/(1+index)` 关联折减（`correlation_discount` 落 `BeliefUpdateRecord`，`belief_update.py:28`）。**但这是"同一来源重复文章"的折减，不是"同一信号跨多个 Belief 的 shared_signal_group"** | 🟡 |
| 依赖结构不得默认线性独立 | `compute_option_scores`（`uncertainty_engine.py`）默认线性加和 `base_utility + Σ(belief_coefficients × probability)`，**无依赖/门/乘法结构** | ❌ |

**对应物**：`evidence_dedup.py` 的 `independence_group`（evidence 级）是 V11 `shared_signal_group` 的**证据侧地基**，但 belief 级共享信号组与因果边完全缺失。

### B.4 Objective/Constraint/Utility 协议 —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| Objective 多目标 + provenance | `Objective`（`domain/objective.py:18-33`）是**单目标**（单 name/metric/direction/weight/priority），`source` 三值；`Decision.objective_id` 单链接。**无多目标、无 ObjectiveProfile** | 🟡 |
| Constraint 单独建模（capital/runway/red_lines，HARD/SOFT） | **无 ConstraintProfile 对象**。`Objective.constraints: list[str]`（`domain/objective.py:27`）只是自由文本列表，非结构化硬/软约束 | ❌ |
| Utility relation 支持 ADDITIVE/MULTIPLICATIVE/THRESHOLD/AND_GATE/OR_GATE/MINIMUM_REQUIRED/INTERACTION/NONLINEAR/UNKNOWN | **纯线性 ADDITIVE**：`compute_option_scores`（`uncertainty_engine.py`）线性加和 + 风险惩罚。`decision_engine.py:65-124` 的 EU 实现无 relation_type、无 gate/threshold。`DecisionOption.belief_coefficients`（`domain/decision.py:25`）是裸 dict[float]，无 provenance | 🟡（仅 ADDITIVE） |
| 硬约束不得被高 Utility 抵消 | 无约束执行层。最接近的是 `opportunity_cost.py:29-59`（把机会成本折进 option）与 `experiment.executability/founder_constraints`（`domain/experiment.py:31-32`，只用于实验排序） | ❌ |

**对应物**：EU 内核已成熟（`decision_engine.py` + `uncertainty_engine.py`），缺的是 V11 Utility Policy 的"**执行前先跑 HARD 约束、按 relation_type 计算、高敏感参数 gate**"这一层。

### B.5 StakesProfile / Adaptive ABSTAIN —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| `StakesProfile`（financial_downside/reversibility/time_to_recover/legal/optionality/risk tolerance/deadline） | **无 StakesProfile 对象**。仅有 `Decision.reversible: bool`（`domain/decision.py:39`）、`DecisionOption.irreversible_cost/opportunity_cost`（`:26-27`）、`Experiment.reversibility: float`（`domain/experiment.py:27`） | ❌ |
| ABSTAIN 阈值随 stakes/reversibility 变化 | **单一全局阈值**：`abstain = margin < minimum_margin or critical_uncertainty > max_critical_uncertainty`（`decision_engine.py:98`），两个阈值对全库所有决策固定（`config.py:90-91`），**无 stakes 分层** | 🟡（有 ABSTAIN，无 adaptive） |
| 每次 HOLD 必须给退出条件/停止研究条件/最晚决策点 | ABSTAIN 时 `rationale.append("acquire decision-changing evidence...")`（`decision_engine.py:102-104`），并强制带 `next_experiment`（ADR-007，`experiment_optimizer.py:4-5`）。**有下一步/停止条件（success/failure/stop_condition 已在 SolveResultV11），但无"最晚决策点/deadline"字段** | 🟡 |
| 低风险可逆动作不应机械 ABSTAIN | 无此区分，所有决策共享同一 margin/uncertainty 门槛 | ❌ |

**对应物**：`decision_sensitivity.py` 的三段鲁棒性阈值（fragile/moderate，`config.py:132-135`）是"推荐翻转距离"分级，**不是 stakes 分级**，二者正交。

### B.6 VOI / 实验价值 —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| 实验价值 = P(改变决策)×改进 − cost − delay − burden（非 information gain） | `experiment_optimizer.py:126-148` 排序公式：`base_score = expected_information_gain × decision_impact × uncertainty × reversibility_bonus × critical_boost / (cost × time_penalty)`，再乘质量因子。**有 `decision_impact` 字段（代理 P(改变决策)）、有 cost/time/reversibility 惩罚；但无显式 option value 项、无 delay cost 独立减法项、无"结果是否会改变行动"的 outcome 场景建模** | 🟡 |
| 每个实验回答"哪种结果会改变决策" | `Experiment` 有 success/failure/ambiguity_criteria（`domain/experiment.py:20-22`）但**无 decision_change_rule/outcome_scenarios**，无法形式化"结果→行动改变"映射 | 🟡 |
| 所有结果都不改变决策 → 默认降级 | 无此逻辑，排序不看"是否改变行动" | ❌ |

**对应物**：`Experiment.decision_impact`（`domain/experiment.py:24`）+ `critical_boost`（`experiment_optimizer.py:127-131`）是 VOI 的朴素代理，但离 V11 的 `ExperimentCandidate.decision_change_rules` 还差一个结构化映射。

### B.7 Sequential Decision / WAIT / STAGE —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| WAIT/STAGE/PILOT/EXPAND/STOP 为正式决策选项 | `DecisionType` = GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION/ABSTAIN（`domain/base.py:120-127`）。**无 WAIT/STAGE/PILOT/STOP/TEST/ACT**。`_map_decision_type` 把 label 含 "wait" 的选项归为 HOLD（`decision_engine.py:200`）——WAIT 被吞并进 HOLD | 🟡 |
| 比较"一次性投 100"vs"先投 5 再投 95" | 无 option value 计算。`opportunity_cost.py:43` 的 `option_value = 0.3 * expected` 是**固定 30% 折扣**，非真正的分期决策期权价值 | ❌ |
| 7 态收敛含 EXPERIMENT_REQUIRED/SEARCH_EXHAUSTED | ✅ 已实现：`convergence_engine.py:27-150` 完整 7 态（NOT_CONVERGED/RESEARCH_MORE/EXPERIMENT_REQUIRED/SEARCH_EXHAUSTED/CONDITIONALLY_CONVERGED/CONVERGED/EXECUTE），且 `research_stop.py` 的 SEARCH_EXHAUSTED 信号已注入（`convergence_engine.py:46-61`） | ✅ |

### B.8 Model Critic —— ❌ 缺失

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| 攻击模型本身：missing variables/hidden dependencies/regime/tail risk，输出 MODEL_MISSPECIFICATION_RISK_HIGH | **全库无 critic/prosecutor/misspecification 概念**（grep 命中为 0）。最接近的是 `capabilities/challenger.py:12-36`：只生成**一条** `LLM_INFERENCE` 反驳证据触发 `conflict_engine`，**不是结构化 ModelCritique，不检查遗漏变量/制度变化/尾部风险，无 MODEL_MISSPECIFICATION_RISK_HIGH 状态** | ❌ |
| Project Prosecutor → Model Critic 升级 | 代码侧的 "ChallengerCapability" 对应的是**旧的 Project Prosecutor（挑战项目内假设）**，未升级到挑战模型本身 | ❌ |
| 高风险决策 gate 要求 CURRENT ModelCritique | 无此 gate | ❌ |

### B.9 Decision Validation / Regret / Decision Ledger —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| Decision Ledger 记 recommendation/action/outcome/model_version，counterfactual 不可识别不伪造 | **无 DecisionRecord 对象**。`PredictionLedger`（`prediction_ledger.py:40-71`）只记**概率预测快照**（belief_snapshot + sha256 hash + policy_version），**不记 recommendation/实际 action/是否采纳/model_version/outcome 关联** | 🟡 |
| 不可变历史，resolve 不改概率 | ✅ 已实现：`resolve()` 不可逆（`prediction_ledger.py:75-111`），`correct()` 生成新版本不改原文（`:113-141`），hash 失配标 CANCELLED（`:89-99`） | ✅ |
| Forecast Calibration 与 Decision Performance 分离 | `calibration_engine.py:43-98`（Brier/ECE/bins）+ `benchmark/metrics.py:46-72`（Brier/ECE）是 Forecast 侧；**Decision Performance 侧只有 `compute_decision_regret`（`metrics.py:102-117`）一个纯函数，且只在 benchmark 用，未进入运行时 ledger，无 action/adoption/regret 持久化** | 🟡 |
| regret 不可识别标 NOT_IDENTIFIABLE 不伪造 | `compute_decision_regret` 对无 utility 标签返回 `None`（`metrics.py:109-115`）——**诚实 N/A 已做到，但没有 CounterfactualStatus 枚举（NOT_IDENTIFIABLE/LOW_CONFIDENCE_ESTIMATE/...）** | 🟡 |

**对应物**：`outcome_settlement_service.py:record_outcome` 把 outcome 落库并 resolve prediction，是"Prediction→Outcome"闭环的地基，但缺 DecisionRecord 这一层把 action/adoption/regret 串起来。

### B.10 EXPLORE/OPERATE 模式 + 默认 5 段输出合同 —— 🟡 部分实现

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| EXPLORE/OPERATE 模式切换 | **全库无 mode 字段**。`SolveRequest`（`runtime.py:93-103`）无 mode；无 Explore/Operate 区分 | ❌ |
| 默认 5 段输出（当前判断/为什么/最大未知/下一步/什么会改变） | `SolveResultV11`（`runtime.py:116-130`）**已含全部 5 段素材**：`decision`+`rationale`（当前判断）、`why`(DecisionTrace)+`belief_snapshot`（为什么）、`critical_uncertainties`（最大未知）、`next_experiment`（下一步）、`what_could_change_my_mind`+`sensitivity`（什么会改变）+ `success/failure/stop_condition` | ✅（素材齐，缺分层投影） |
| Progressive Disclosure（默认隐藏 prior/posterior/utility，Advanced 才展开） | 无 DTO 分层，`/v1/solve`（`api.py:491-495`）把 `SolveResultV11.model_dump()` 全量返回，**无 Default/Advanced 两套投影** | ❌ |

### B.11 ACT/EXPERIMENT/WAIT/HOLD/PIVOT/KILL 状态词 —— 🟡 部分实现

| V11 状态词 | 代码现状 | 判定 |
|---|---|---|
| HOLD / PIVOT / KILL | ✅ `DecisionType.HOLD/PIVOT/KILL`（`domain/base.py:123-125`）；`ProjectStatus` 有 `HOLD/PIVOTING/KILLED`（`domain/project.py:18-20`） | ✅ |
| ABSTAIN | ✅ `DecisionType.ABSTAIN`（`base.py:127`），作为内部 reasoning state（`decision_engine.py:99-101`） | ✅ |
| ACT | ❌ 无 ACT；对应语义是 `GO`（`base.py:121`） | 🟡 |
| EXPERIMENT / TEST | ❌ 无；实验是独立对象 `Experiment`，不是 DecisionType；`ConvergenceStatus.EXPERIMENT_REQUIRED`（`base.py:133`）是收敛态非行动态 | ❌ |
| WAIT | ❌ 无；被 `_map_decision_type` 吞并进 HOLD（`decision_engine.py:200`） | ❌ |
| STOP | ❌ 无；最接近是 KILL | ❌ |
| GO/CONDITIONAL_GO/SELECT_OPTION | ✅ 代码自有（非 V11 词表，是 v1.1.x 词表） | ✅ |

**结论**：v1.1.2 的决策词表（GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION/ABSTAIN）与 V11 的 ActionState（ACT/TEST/HOLD/WAIT/STOP）+ option 语义（PIVOT/KILL）**是两个正交的词表**，存在 `ABSTAIN↔(HOLD/TEST/WAIT)` 的语义映射需求，但代码侧从未做前台映射。

### B.12 Prompt Stack / 分层注入 —— ❌ N/A（代码侧对应物是确定性引擎）

| V11 要求 | 代码现状 | 判定 |
|---|---|---|
| 7 层 Prompt Stack（Hard Rules→Constitution→Decision Protocol→Mode→Specialist→Context→Output Contract） | **代码侧无 prompt stack**。`DecisionCompiler.compile` 把 `task`+`schema={"kind":"compile_decision"}`+`context` 三件套发给 `model.generate_structured`（`capabilities/__init__.py:74-83`），是单段 prompt，非分层拼装 | ❌（架构层面） |
| 每条规则唯一权威来源，禁止 Addendum 重复追加 | v1.1.2 的"权威来源"是**代码本身**（Repository 唯一写入口 + 确定性引擎 + 枚举集中定义 `domain/base.py`），Capability/Provider 是候选产出者无写权（`capabilities/base.py`、`providers/factory.py`） | ✅（哲学同构） |
| 确定性规则从 LLM 移出到 Runtime | ✅ 已实现：dedup/belief/decision/convergence/experiment/calibration 全部是**纯函数引擎**，LLM 只产出候选结构 | ✅ |

**核心观察**：V11 的 "Prompt Stack 第 3 层 Decision Model Protocol + Runtime Policies" 在 v1.1.2 中**已经物化为 `runtime/` 下 28 个确定性引擎**，而不是 prompt 文本。V11 自己 §8 也承认"Belief causal graph / Utility 非线性 / Adaptive ABSTAIN / VOI / Regret 均**不能仅靠 Prompt 解决，必须进 Runtime**"。所以这一项的正确映射是：**V11 的 Prompt Stack = v1.1.2 的"确定性引擎 + Capability 无写权边界"的 prompt 侧投影，二者是同一哲学的两个表达，不是"代码缺 prompt"**。

---

## C. 可吸收增量 P0 排序（与上一轮 5 P0 + 9 P1/P2 合并）

**合并原则**：上一轮的 5 P0 是"已承诺未兑现的工程正确性"（env 名漂移 / decision_sensitivity_signal 空转 / PG 无测试 / API envelope 两套 / prediction 双重写），**必须优先于 V11 的任何新功能**——它们便宜且是"止血"。V11 增量是"语义层新增"，按"先 schema 后 runtime 后 critic"排序。

| 排序 | 来源 | 项 | V11 要求 | 当前代码差距 | 落地建议 | 预估收益 |
|---|---|---|---|---|---|---|
| **M0** | 上轮 P0×5 | 工程止血 5 项 | （见上轮报告 §7） | `config.py:167`/`runtime.py:483-491`/`migrations`/`api.py`/`prediction_ledger.py:69` | 照上轮清单执行，**不改 V11 语义** | 消除隐性事故，是引入 V11 语义的前提 |
| **V-1** | 新 | **calibration_status 5 态 + EstimateType + 参数 provenance** | G-02/G-03/G-14；Schema §3 CalibrationStatus/EstimateType/ProvenanceType | `CalibratedConfidence.status` 仅 2 态（`calibration.py:42`）；`Belief`/`DecisionOption` 无 provenance；`Objective.source` 三值 | ① `domain/calibration.py` 扩 5 态枚举；② `domain/belief.py` 加 `estimate_type`+`calibration_status`；③ `domain/decision.py:25` 给 `belief_coefficients` 换 `ModelParameter(value,provenance,status,approved_by)`；④ `capabilities/__init__.py:87-92` 编译产物默认 `LLM_PROPOSED/PROPOSED`，加 approval gate | 最高：V11 全部语义的"地基"，改动小、可立即验证 |
| **V-2** | 新 | **Decision Ledger（action/adoption/outcome/regret 关联）** | Protocol 10；DecisionRecord/OutcomeRecord | `prediction_ledger.py` 只存概率快照；`metrics.py:102` 的 regret 只在 benchmark | ① 新增 `domain/decision_ledger.py`（DecisionRecord: recommendation/action_taken/model_version/abstain_reason + OutcomeRecord: regret_estimate/counterfactual_status）；② `runtime.py` solve 落地时写 DecisionRecord；③ `outcome_settlement_service.py` 回填 outcome+regret（不可识别标 NOT_IDENTIFIABLE） | 高：兑现 V11 最高价值主张"长期验证减少 regret"，且不重写现有引擎 |
| **V-3** | 新 | **Model Critic 结构化升级** | Protocol 09；ModelCritique/MODEL_MISSPECIFICATION_RISK_HIGH | `capabilities/challenger.py:12-36` 只产 1 条反驳证据 | ① 新增 `domain/critic.py`（ModelCritique: missing_variables/hidden_dependencies/regime_risks/double_counting/model_risk）；② ChallengerCapability 输出结构化 critique；③ 高风险 solve 前加 critic gate（初版用 config 阈值触发） | 高：直接阻断"在错误模型上提高精度"，且 Challenger 已有挂点 |
| **V-4** | 新 | **StakesProfile + Adaptive ABSTAIN** | Protocol 07/08；G-07 | `decision_engine.py:98` 单一全局阈值 | ① 新增 `domain/stakes.py`（StakesProfile 8 维 + StakesClass）；② `config.py` 增加按 stakes 分层的阈值带；③ `decision_engine.evaluate` 按 stakes_class 查阈值；④ ABSTAIN 输出带 deadline/exit/stop（SolveResultV11 已留 stop_condition/success/failure 字段） | 高：解决"ABSTAIN 疲劳"，且 Stakes Runtime Policy 已给出可直译的分类算法 |
| **V-5** | 新 | **Utility 关系类型（THRESHOLD/AND_GATE/MULTIPLICATIVE）** | Protocol 06；Utility Runtime Policy | `compute_option_scores` 纯线性加和 | ① `domain/utility.py` 新增 UtilityComponent(relation_type,coefficient,threshold)；② `uncertainty_engine.py` 按 relation_type 执行（至少先实现 AND_GATE/THRESHOLD 阻断，MULTIPLICATIVE 次之）；③ 硬约束先于 Utility | 高：修复"WTP 高 + Distribution≈0 仍线性高分"的结构性缺陷（回归 C04） |
| **V-6** | 新 | **BeliefEdge 因果图 + shared_signal_group** | Protocol 05；G-05/G-06 | 无 BeliefEdge；`evidence_dedup.py` 的 `independence_group` 是 evidence 级 | ① 新增 `domain/belief_edge.py`（BeliefEdge 9 类 relation）；② `evidence.py` 加 `shared_signal_group`；③ belief 聚合时按边关系防 double counting（在 `belief_engine.py` 的 discount 上扩展） | 中：防 double counting 从"证据级"升到"信念级" |
| **V-7** | 新 | **ActionState 词表 + WAIT/STAGE 选项 + 5 段输出投影 + EXPLORE/OPERATE** | Protocol 02/07/12；G-08/G-10/G-15 | `DecisionType` 缺 WAIT/TEST/STAGE/STOP/ACT；`SolveResultV11` 素材齐但无 mode/分层 | ① `domain/base.py` 扩 `ActionState`（ACT/TEST/HOLD/WAIT/STOP）；② DecisionOption 支持 WAIT/STAGE kind；③ `runtime.py` 加 mode 字段 + Default/Advanced 两层 DTO 投影 | 中：UX 收益大但依赖 V-1/V-4 先行 |

**关键判断**：V-1~V-5 是 V11 的"科学正确性内核"（对应蓝图 §0.2.1 "Core Correctness 先于 Explore Expansion"），V-6/V-7 是"体验与因果深化"，应排在后面。**V11 的 Explore Expansion（Founder/Opportunity/Venture 等 8 个 Specialist）不进入本轮 P0**——蓝图自己裁定"先修 Kernel 再扩服务范围"（蓝图 §0.2.1），且上一轮已确认 8 个 capability 是 mock 桩。

---

## D. 裁决建议（给主理人/用户）

### D.1 V11 是否值得作为 v1.2 的正式输入？

**值得，但只采纳它的"语义协议 + Runtime Policy"，不采纳它的"Prompt 文本"作为交付物。**

三个理由：
1. **与 v1.1.2 哲学天然同源**。V11 的核心句 "LLM proposes; schema constrains; runtime governs; ledgers preserve history"（Schema §0）就是 v1.1.2 三层架构（Repository 唯一写入口 / 确定性引擎 / Capability 无写权）的书面化。V11 的 G-03（LLM propose ≠ approve）、G-12（auto-ingest ≠ auto-influence）、G-13（forecast calibration ≠ decision quality）、counterfactual honesty——**v1.1.2 已在代码里用"确定性引擎 + 不可变 ledger + 诚实 N/A"实现了对应物**。
2. **V11 的增量恰好补 v1.1.2 最薄弱的一块**：v1.1.2 有非常强的"确定性计算"和"不可变持久化"，但**缺"语义标注层"**——参数无来源、概率无状态、Belief 无关系、阈值无分层、决策无 regret 复盘。V11 提供的正是这套标注语义。
3. **V11 自己已诚实宣告"Prompt 不是瓶颈"**：Full System Prompt 回归报告 §7 明写 *"further broad prompt rewriting has diminishing return; the next quality jump comes from executable schemas, deterministic services, mutation permissions and automated regression"*，§8 判 *"Production Decision Runtime NOT TESTED / Production release NO-GO YET"*。

### D.2 天然吻合 vs 天然冲突

**天然吻合**（可直接吸收，无理念摩擦）：
- LLM 无写权 / 参数治理（G-03）↔ Capability 无写权 + Repository 单写入口
- 确定性阈值 policy versioned（G-14）↔ `config.py` 全阈值可 env 覆盖 + `policy_version`
- Forecast vs Decision Performance 分离（G-13）↔ `calibration_engine` 与 `metrics.compute_decision_regret` 已是两个独立函数
- 证据晋级治理（G-12）↔ `evidence_policy.py` 的 authority/verification gate + `binding` 四态
- counterfactual 不伪造（Protocol 10.4）↔ `compute_decision_regret` 返回 None 的诚实 N/A

**天然冲突 / 需要裁决的张力**（不是敌对，是"表达层次不同"）：
- **V11 是 Prompt 架构，v1.1.2 是代码架构**。V11 的 7 层 Prompt Stack 在 v1.1.2 里**没有对应物也不需要对应物**——因为 v1.1.2 把"确定性规则"从 LLM 移到了 `runtime/` 引擎。V11 §8 自己承认多数规则"不能仅靠 Prompt 解决"，所以这不是真冲突，而是**"把 prompt 层协议降级为 domain schema + 确定性服务"的映射问题**。
- **状态词表不兼容**：v1.1.2 用 GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION/ABSTAIN，V11 用 ACT/TEST/HOLD/WAIT/STOP + option 语义。需显式映射（ABSTAIN→HOLD/TEST/WAIT），不能混用。
- **阈值哲学不同**：v1.1.2 是"全局固定阈值"（`config.py` 单一 minimum_margin/max_critical_uncertainty），V11 是"按 stakes/domain 分层的 versioned policy"（G-14）。这是 V-4 要改的核心。

### D.3 版本策略建议

**继续"蓝图 → 施工图 → 代码"落地路线，不要"prompt 文档驱动"。**

具体到 v1.2 的路线（与 v1.1.x 完全同构）：
1. **Phase 1（Schema）**：把 V11 Schema v0.2 的 19 对象 + 18 枚举，**只取 v1.1.2 缺失的部分**，映射为 `domain/` 新增模块（calibration_status 5 态、parameter provenance、StakesProfile、DecisionRecord/OutcomeRecord、BeliefEdge、ModelCritique、UtilityComponent）——**复用现有 `VencertiaBaseModel`（extra=forbid + validate_assignment），不新建独立 `schemas_v11/` 包**（避免与 92 py 现有 domain 割裂）。
2. **Phase 2（Runtime）**：把 V11 的三个 Runtime Policy（Stakes/Utility/Evidence Aggregation）转成 `runtime/` 新引擎（StakesEvaluationService / UtilityExecutionService / SignalAggregation），沿用"确定性纯函数 + 引擎 bundle 装配"的既有模式（`container.py` 的 Composition Root）。
3. **Phase 3（回归）**：把 V11 的 40 个语义场景（R01-R40）转成 `benchmark/` 的确定性夹具（像现有 `test_integrity_v112.py` 把验收点映射成测试那样），而不是停留在 prompt 文案。
4. **明确不做**：不重写 15 份 Prompt 为 7 层 Stack 文本；不扩 Explore 的 8 个 Specialist（蓝图自己裁定后置）；不迁移 `full_pack/` 重复版本。

**一句话裁决**：*AgentV11 是 v1.2 的"语义升级需求书"，不是"交付物清单"——采纳它的 provenance/calibration/Stakes/ModelCritic/DecisionLedger 五组协议，落成 domain 对象 + 确定性服务 + 回归夹具，而非继续堆 prompt。*

---

## 附：方法与局限

- **方法**：`Read` 主蓝图 V2（519 行全读）+ Core Protocol Pack v0.1（813 行全读）+ Core Patch（250 行全读）+ Schema v0.2（前 220 行 + 枚举表）+ 三个 Runtime Policy + Full System Prompt 回归报告；代码侧 `Read` domain 15 文件、runtime 引擎 12 文件、benchmark 3 文件、config/container/capabilities；`Grep` 定向验证 5 组关键符号（provenance/calibration_status/stakes/shared_signal/regret/WAIT/critic 等）在 `src/` 的存在性。
- **局限**：① Schema v0.2 未逐行读完 3084 行（对象字段细节以蓝图 §4 + 枚举表 §3 为准）；② 8 个 Specialist v0.1 与 `full_pack/` 22 文件仅归类未逐字审计（多为重复版本）；③ 代码侧 `runtime.py`(51k)/`research_service.py`(26k) 等长文件读关键段落，未逐行穷尽；④ 本报告是"语义映射"审查，未运行任何代码，运行时数字（417 passed/ruff）沿用上一轮"未验证"结论。
