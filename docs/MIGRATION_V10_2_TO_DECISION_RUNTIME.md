# V10.2 → Decision Runtime 迁移映射（Migration Mapping）

> 目的：把 AgentV10.2 Full Release（User Knowledge Runtime V1.0 + Company Intelligence Runtime V1.1 + 15 份 Prompt）的**语义资产**无损映射到 v1.0 Decision Runtime 的 canonical 对象，并提供导入工具的映射依据。
> 原则：**保留语义、删除 Agent 权威、字段继承、不破坏原资产**（导入是只读的）。

---

## 1. 总览：三类迁移

| 迁移类型 | 内容 | 工具 |
|---|---|---|
| A. 域对象映射 | V10.2 对象 → 新 canonical 对象（见 §2 表） | `src/vencertia/legacy/mapping.py`（纯函数映射字典） |
| B. 资产导入 | 从 V10.2 release 目录读取 JSON/DOCX 资产 → 生成新域对象导入脚本 | `src/vencertia/legacy/import_v10_2.py` |
| C. 运行时桥 | 新 runtime 兼容读取旧 Memory/ContextBundle（读投影，不双写） | `runtime/context.py`（ContextBuilder 简化版） |

---

## 2. 域对象映射表（V10.2 → v1.0）

### 2.1 用户知识域

| V10.2 对象/字段 | v1.0 canonical 对象 | Migration method |
|---|---|---|
| `MemoryRecord`（memory_id/user_id/project_id/scope/memory_type/content/structured_value/source_message_ids/source_entity_ids/evidence_ids/fact_status/confidence/importance/status/created_at/updated_at/valid_from/valid_to/supersedes_memory_id/conflicts_with_memory_ids） | `MemoryRecord`（原样保留字段语义） | 1:1 直接导入；`fact_status: FactStatus` → `Verification` 枚举值映射（VERIFIED/ESTIMATED/ASSUMED/UNKNOWN 同名） |
| `MemoryScope` | `MemoryScope` | 原样保留 |
| `MemoryType`（21 值） | `MemoryType` | 原样保留 |
| `MemoryStatus` | `MemoryStatus` | 原样保留 |
| `MemoryOperation`（WRITE/MERGE/SUPERSEDE/CONFLICT/REJECT/EXPIRE/ARCHIVE） | `MemoryOperation` | 原样保留 |
| `AccessClass`（PRIVATE/INTERNAL/MATCHABLE/PUBLIC） | `AccessClass` | 原样保留 |
| `ProperStore`（11 类） | 新系统用 `proper_store` 字符串字段（暂不建表） | 映射：STABLE_MEMORY→memory_records；FOUNDER_PROFILE→founder_profiles；PROJECT_KB→project_kb；EVIDENCE_LEDGER→evidence；ASSUMPTION_LEDGER→claims(assumption)；EXPERIMENT_LEDGER→experiments；ACTION_LEDGER→actions；DECISION_LEDGER→decisions；FINANCIAL_SNAPSHOT→financial_snapshots；CUSTOMER_FEEDBACK→evidence(customer)；STARTUP_INTELLIGENCE→company_cases |
| `MemoryCandidateEnvelope` | `MemoryCandidate`（新，加 semantic_key/access_class/proper_store） | 字段合并；`source_types` 保留 |
| `MemoryPermission` | `AccessClass` 字段（v1.0 简化为字段级，不做独立表） | 折叠 |
| `MemoryConflict` | `ConflictAlert`（Belief/Evidence 层）或保留 memory_conflicts 表 | 映射为通用 conflict 记录 |
| `ContextBundle` | `ContextBundle`（读投影，runtime/context.py） | 保留 DTO 语义；**不持久化** |

### 2.2 创始人域

| V10.2 对象/字段 | v1.0 canonical 对象 | Migration method |
|---|---|---|
| `FounderProfile`（由 Founder domain service 维护，V10.2 只触发刷新信号） | `FounderProfile` + `FounderState` | 拆分：稳定属性 → FounderProfile；时变属性（runway/time/energy…）→ FounderState |
| MemoryType.FOUNDER_FACT/RESOURCE/CAPABILITY/CONSTRAINT/RED_LINE/PREFERENCE | FounderProfile 字段（skills/network/domain_expertise/sales_ability/risk_tolerance/capital_access/motivation/execution_reliability/constraints/red_lines/preferences） | 语义提取（`founder_profile_sync.py` 逻辑迁移）；原始 MemoryRecord 保留 |
| `requires_founder_profile_refresh` | FounderState 刷新触发（event: PROJECT_STATE_CHANGED） | 迁移为事件订阅 |

### 2.3 项目/决策域

| V10.2 对象/字段 | v1.0 canonical 对象 | Migration method |
|---|---|---|
| Project Status（IDEA/EXPLORING/VALIDATING/ACTIVE/PIVOTING/HOLD/KILLED/ARCHIVED） | `Project.status` | 原样保留 |
| Startup Stage（S0_INITIALIZATION…S9_SCALE_OR_DECISION） | `Project.stage` | 原样保留 |
| Strategic Decision（GO/CONDITIONAL_GO/PIVOT/HOLD/KILL） | `DecisionType`（+SELECT_OPTION/ABSTAIN） | 扩展保留 |
| Primary/Backup/Held/Killed candidates（S5 收敛） | `Project.is_primary` + `Project.status` | 0/1 primary 不变式；KILLED 不能 primary |
| Hard Gate ≥4/5、Score ≥75、7-14 天验证窗口 | `Rule`（INVARIANT/POLICY/HEURISTIC 三层） | 规则化：`hard_gate_score` Policy、`validation_window_days` Heuristic、`killed_not_primary` Invariant |
| `Assumption`（Assumption Ledger） | `Claim(claim_type=HYPOTHESIS/ASSUMPTION)` + `Belief` | Assumption→Claim；量化状态→Belief |
| `Evidence`（Evidence Ledger） | `Evidence`（新字段：authority_level/scope/relevance/conflict_status/transferability） | 字段升级映射（见 §2.5） |
| `Experiment`（Experiment Ledger） | `Experiment`（+success/failure/ambiguity_criteria/status） | 字段扩展 |
| `Action`（Action Ledger） | `Action` | 原样保留语义 |
| `Decision`（Decision Ledger） | `Decision`（+convergence_status/snapshot_hash/critical_uncertainty_ids） | 字段扩展 |
| State Transition Engine 判定 | `ConvergenceEngine` + `DecisionEngine`（确定性） | 迁移为确定性引擎，Prompt 判定权移除 |

### 2.4 财务/公司智能域

| V10.2 对象/字段 | v1.0 canonical 对象 | Migration method |
|---|---|---|
| `FinancialSnapshot` | `FinancialSnapshot` | 原样保留；版本化（version 字段） |
| `Company Case V1.4`（company identity/operating segments/offers/snapshot/revenue streams/claims/evidence/sources） | `CompanyCase`（子集） | 导入为 CompanyCase + Claim + Evidence（scope=COMPANY_CASE） |
| `CaseUnitRef`（company_id/snapshot_id/segments/offers/revenue_streams/customer_segments/geography/valid_period） | `CaseUnitRef` | 原样保留 |
| `FounderRecord`（公开案例创始人） | `FounderRecord` | 原样保留（注意：≠ 用户 FounderProfile，隔离） |
| `FundingRound` | `FundingRound` | 原样保留（**不是需求证据**，隔离） |
| `ClaimTraceResult`（SUPPORTED/PARTIAL/CONFLICTED/REJECTED/STALE/UNKNOWN） | `ClaimTrace` | 原样保留 |
| Transferability（V3 §33.6） | Evidence.transferability + EvidencePolicy 判定 | 关系属性挂 Evidence |
| Case eligibility（FACT_READY/…/Eligibility by Use） | Rule（POLICY）+ benchmark 准入 | 迁移为 Policy |

### 2.5 Evidence 映射细节

| V10.2 Evidence 概念 | v1.0 Evidence 字段 | 说明 |
|---|---|---|
| SourceType（memory：USER_EXPLICIT_INPUT/USER_CORRECTION/CUSTOMER_FEEDBACK/EXPERIMENT_RESULT/REAL_PAYMENT/PROJECT_DECISION/AGENT_INFERENCE/DOCUMENT_CLAIM/WEB_SOURCE/SYSTEM_DERIVED/TOOL_RESULT） | `EvidenceType` + `authority_level` | 映射：REAL_PAYMENT→PROJECT_REALITY；EXPERIMENT_RESULT→PROJECT_EXPERIMENT_RESULT；CUSTOMER_FEEDBACK→CUSTOMER_COMMITMENT_OR_PAYMENT 或 PROJECT_DIRECT_BEHAVIOR；AGENT_INFERENCE→LLM_INFERENCE；DOCUMENT_CLAIM/WEB_SOURCE→REVIEWED_EXTERNAL_RESEARCH（待校验）；SYSTEM_DERIVED→SYSTEM_DERIVED |
| V3 Appendix A 证据强度（11 级） | `AuthorityLevel`（9 级） | 合并相邻层级（EXECUTIVE_STATEMENT+FOUNDER_JUDGMENT→FOUNDER_STATEMENT；MEDIA 归入 REVIEWED_EXTERNAL_RESEARCH 低端） |
| `supports_claim/contradicts_claim`（ClaimTrace） | `supports_or_contradicts` | 合并为单字段 Direction |
| `SourceQuality/Freshness`（ClaimTrace） | `reliability` + `observed_at` | 数值化 |
| Verification（V10.2 FactStatus） | `Verification` | 原样保留 |

---

## 3. Prompt → 能力模块映射（A0–A10）

| V10.2 Prompt | v1.0 去处 | 迁移方法 |
|---|---|---|
| A0 Orchestrator | `SolveOrchestrator`（确定性编排） | 编排逻辑 → runtime；对话式判断权移除 |
| A1 Founder Diagnosis | `capabilities/founder_diagnosis.py`（inference） | 输出候选 FounderState 特征；不写 FounderProfile |
| A2 Market Opportunity | `capabilities/market.py` | 输出候选 Evidence（REVIEWED_EXTERNAL_RESEARCH/MODEL_PRIOR） |
| A3 Venture Design | `capabilities/gtm.py`（+decision compile 输入） | 输出候选 DecisionOption/Experiment 候选 |
| A4 Project Prosecutor | `capabilities/challenger.py` | 输出反驳证据/反假设；触发 CONFLICT 检测 |
| A5 Financial & Business Model | `capabilities/financial.py` | 输出 FinancialSnapshot 候选/unit economics |
| A6 Execution Strategy | `capabilities/gtm.py`（+action 规划） | 输出候选 Action；不直接执行 |
| A7 Next Action | `ExperimentOptimizer`（确定性） | Prompt 判定 → 确定性公式 |
| A8 Startup Case Intelligence | `capabilities/company_intelligence.py` | 输出 CompanyCase/ClaimTrace；遵守 Company Case 隔离 |
| A9 Founder Matchmaking | 占位（v1.0 不做） | 保留接口注释 |
| A10 Business Plan Architect | 占位（下游投影，非 truth） | 保留接口注释 |
| Routing | `providers/models.py` + capability 选择器（简单确定性路由） | 路由 = 函数选择，非业务权威 |
| State Transition | `ConvergenceEngine` + `ProjectService` | 确定性状态机 |
| Memory Write | `events/` + `runtime/context.py`（MemoryCandidate 事件化摄入） | 候选 → 事件 → MemoryManager 判定（保留 V10.2 逻辑） |
| Pydantic JSON Schema | `domain/` 全量（pydantic v2 导出） | 已执行 |

---

## 4. 不变式继承清单（V10.2 → v1.0）

| V10.2 不变式 | v1.0 对应 |
|---|---|
| 硬门槛 > 分数（Hard Gate > Score） | Invariant 优先于 Policy/Heuristic |
| 现实市场 > Agent 意见（Real Market > Agent Opinion） | authority 层级 |
| 付款 > 兴趣（Payment > Interest） | PROJECT_REALITY > CUSTOMER_COMMITMENT |
| 阶段必须挣得（Stage Must Be Earned） | 阶段迁移必须有证据（ProjectService 校验） |
| 时间不推进状态 | 无时间自动迁移 |
| 回滚允许（Rollback Is Allowed） | Stage/status 状态机含回滚边 |
| 负面证据必须改变状态 | Outcome → Belief → Decision 链 |
| Unknown 保持 Unknown | ABSTAIN/SEARCH_EXHAUSTED 不强制结论 |
| KILLED 不能 Primary | Invariant（killed_not_primary） |
| 融资不是需求证据 | FundingRound 隔离（Company Case 域） |
| Context 是读投影 | ContextBundle 不持久化 |

---

## 5. 导入工具输入/输出

```bash
# 用法（T05 交付）
vencertia migrate-v10.2 \
  --source legacy/agent_v10_2/AgentV10.2/Vencertia_AgentV10.2_Full_Release \
  --db vencertia.db \
  --dry-run
```

```python
# src/vencertia/legacy/import_v10_2.py
class V10_2Importer:
    def __init__(self, source_dir: Path, repo: Repository, policy: EvidencePolicy): ...
    def scan(self) -> ImportManifest: ...          # 列出可导入资产
    def import_memory(self) -> ImportReport: ...   # MemoryRecord 导入
    def import_company_cases(self) -> ImportReport: ...  # Company Case → CompanyCase + Claim + Evidence
    def import_rules(self) -> ImportReport: ...    # Hard Gate/Score/7-14天 → Rule
    def dry_run(self) -> ImportReport: ...         # 不写库
```

验收要点：
- 导入对原 release 目录**只读**；
- 同 id 幂等（重复导入不产生重复记录）；
- 每个导入对象生成 `ImportManifestEntry{source_ref, canonical_type, canonical_id, mapping_version, warnings}`；
- `--dry-run` 输出 mapping 覆盖率（≥ 95% 核心对象）。
