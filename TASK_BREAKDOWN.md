# TASK_BREAKDOWN — Vencertia Adaptive Decision System v1.0（工程师施工图）

> 版本：1.0（设计基线）
> 阅读顺序：先读 `docs/architecture.md` + `docs/domain-model.md`，再按本文件任务顺序实现。
> 任务总量：**5 个任务（T01–T05）**，按层次分组（不按单文件拆分）。每个任务包含：文件路径 / 模块职责 / 依赖 / 关键接口签名 / 验收要点。
> 迭代节奏：实现按 T01→T05 顺序推进；**3 轮工程迭代**设计见 §10。

---

## 任务总览

| ID | 任务 | 层次 | 依赖 | 优先级 |
|---|---|---|---|---|
| T01 | 项目基础设施与工程骨架 | 工程 | — | P0 |
| T02 | 领域层 + 持久层 + 事件 + V10.2 导入（REALITY 全量） | REALITY | T01 | P0 |
| T03 | Runtime 确定性引擎全量 | DECISION INTELLIGENCE | T02 | P0 |
| T04 | Capability 骨架 + Providers（mock） | CAPABILITY | T02 | P0 |
| T05 | API/CLI + Benchmark + Demo + 文档 + 集成验证 | 接口/交付 | T03, T04 | P0 |

---

## T01 — 项目基础设施与工程骨架

**依赖**：无

### 文件

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | 依赖声明（最小集：pydantic/fastapi/uvicorn/typer/rich/httpx/pytest；`psycopg[binary]` 为 optional extra `postgres`）；`[project.scripts] vencertia = "vencertia.cli:app"`；版本 `1.0.0` |
| `Makefile` | `make install` / `make test` / `make benchmark` / `make demo` / `make api` / `make verify` |
| `src/vencertia/__init__.py` | 版本导出 `__version__ = "1.0.0"`；包路径声明 |
| `src/vencertia/config.py` | `Settings`：`db_dsn`（默认 `sqlite:///vencertia.db`）、`postgres_dsn`（None 则禁用 PG）、`model_provider`（默认 mock）、`openai_base_url/api_key/model`、`policy_version`、`log_level`；`get_settings()` 懒加载 |
| `src/vencertia/events/__init__.py` | 事件总线骨架（完整事件类型在 T02 实现，此处先留 `EventType` 枚举空壳？→ 否，直接放完整 `types.py` 于 T02；此处只放 `bus.py` 最小骨架） |
| `src/vencertia/events/bus.py` | `EventBus`：`publish(event)` / `subscribe(handler)` / `handlers_for(type)`；同步内存实现 |
| `tests/conftest.py` | pytest fixtures：`tmp_db`（临时 SQLite 路径）、`settings`、`event_bus` |
| `.env.example` / `.gitignore` | 环境样例与忽略规则 |
| `README.md`（替换 v0.1 版） | 项目定位、安装、快速开始（demo/benchmark/api）、文档索引、v1.0 与 v0.1 差异 |

### 关键接口签名

```python
# src/vencertia/config.py
@dataclass(frozen=True)
class Settings:
    db_dsn: str = "sqlite:///vencertia.db"
    postgres_dsn: str | None = None
    model_provider: str = "mock"          # mock | openai_compatible
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    policy_version: str = "1.0"
    log_level: str = "INFO"
    @classmethod
    def from_env(cls) -> "Settings": ...
def get_settings() -> Settings: ...       # lru_cache

# src/vencertia/events/bus.py
class EventBus:
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: EventType, handler: Callable[[DomainEvent], None]) -> None: ...
```

### 验收要点

- `pip install -e .` 成功；`vencertia --help` 可运行（CLI 主体在 T05，此处允许 stub 输出）。
- `make test` 跑通空测试（conftest 可用）。
- `Settings.from_env()` 正确读取环境变量；无 PG DSN 时 `postgres_dsn is None`。
- 事件总线单元测试：publish/subscribe/handlers_for 通过。

---

## T02 — 领域层 + 持久层 + 事件 + V10.2 导入（REALITY 全量）

**依赖**：T01

### 文件（一）— 域模型 `src/vencertia/domain/`

| 文件 | 职责 |
|---|---|
| `base.py` | `VencertiaBaseModel`（`extra="forbid"` 等）、`utcnow()`、公共枚举：`Scope/EvidenceType/AuthorityLevel/Verification/Direction/ConflictStatus/ClaimType/ClaimStatus/UpdateMethod/DecisionType/ConvergenceStatus/ExperimentStatus/PredictionResolution/ActionStatus/OutcomeType/RuleKind`（字段见 domain-model.md §1） |
| `objective.py` | `ObjectiveDirection`、`Objective` |
| `claim.py` | `Claim` |
| `evidence.py` | `Provenance`、`Evidence`（含 `authority_level`、`transferability`） |
| `belief.py` | `Belief`（alpha/beta/prior/posterior/uncertainty/confidence/update_method/calibration_group）、`EvidenceApplication`、`ConflictAlert` |
| `decision.py` | `DecisionOption`、`Decision`、`DecisionResult`、`OptionScore` |
| `experiment.py` | `Experiment`、`RankedExperiment`、`ExperimentStatus` |
| `action_outcome.py` | `Action`、`Outcome`、`OutcomeType` |
| `prediction.py` | `PredictionEntry`、`PredictionResolution` |
| `calibration.py` | `CalibrationScope`、`CalibrationProfile` |
| `project.py` | `ProjectStatus`、`Stage`、`Project`、`ProjectKB` |
| `founder.py` | `FounderProfile`、`FounderState`、`Opportunity`、`FounderOpportunityPortfolio` |
| `company.py` | `CompanyCase`、`CaseUnitRef`、`FounderRecord`、`FundingRound`、`ClaimTrace`（继承 V10.2 契约） |
| `memory.py` | `MemoryScope/MemoryType/MemoryStatus/MemoryOperation/AccessClass`、`MemoryRecord`、`MemoryCandidate`（继承 V10.2） |
| `policy.py` | `Rule`、`RuleKind`、`RuleSet`（按 kind 分组查询） |
| `convergence.py` | `ConvergenceReport`、`CriticalUncertainty`、`ConvergenceStatus` |

### 文件（二）— 事件 `src/vencertia/events/`

| 文件 | 职责 |
|---|---|
| `types.py` | `EventType`（12 类：EVIDENCE_ADDED/BELIEF_UPDATED/DECISION_CREATED/DECISION_EVALUATED/EXPERIMENT_PROPOSED/EXPERIMENT_RESOLVED/ACTION_CREATED/OUTCOME_RECORDED/PREDICTION_CREATED/PREDICTION_RESOLVED/CALIBRATION_UPDATED/PROJECT_STATE_CHANGED）、`DomainEvent`（含 payload/actor/occurred_at） |
| `bus.py`（T01 升级） | 完整实现：发布、订阅、`publish_many`、事件序号 |

### 文件（三）— 持久层 `src/vencertia/repositories/`

| 文件 | 职责 |
|---|---|
| `base.py` | `Repository` 协议（见下）+ `StaleWriteError` + `EntityNotFoundError` |
| `sqlite.py` | `SQLiteRepository`：全量 CRUD（evidence/claims/beliefs/decisions/experiments/actions/outcomes/predictions/projects/objectives/founder profiles/financial snapshots/company cases/memory records/rules/events）；乐观锁（version 检查）；事务 |
| `postgres.py` | `PostgresRepository`：接口与 SQLite 一致；**DSN 门控**（`postgres_dsn is None` 时 import/实例化抛 `PostgresDisabledError`）；psycopg3 实现 |
| `memory.py` | `InMemoryRepository`：测试用，语义同 SQLite |
| `migrations/0001_initial.sql` | SQLite 建表 DDL（幂等 `CREATE TABLE IF NOT EXISTS`）；`migrations/0002_pg.sql` 为 PG 版（类型适配） |
| `migrations/__init__.py` | `run_migrations(conn, backend)` 帮助函数 |

### 文件（四）— V10.2 导入 `src/vencertia/legacy/`

| 文件 | 职责 |
|---|---|
| `mapping.py` | 纯函数映射字典：V10.2 对象/字段 → v1.0 域对象（依据 docs/migration-v10.2-to-decision-runtime.md §2 表）；`map_memory_record()/map_evidence()/map_company_case()/map_rules()` 等 |
| `import_v10_2.py` | `V10_2Importer`：扫描 release 目录（MemoryRecord JSON/Company Case/JSON Schema/规则），幂等导入（同 id 不重复），`--dry-run` 报告 mapping 覆盖率；对源目录只读 |

### 关键接口签名

```python
# repositories/base.py
class Repository(Protocol):
    def add_evidence(self, e: Evidence) -> None: ...
    def get_evidence(self, evidence_id: str) -> Evidence | None: ...
    def add_claim(self, c: Claim) -> None: ...
    def get_beliefs(self, project_id: str, as_of: datetime | None = None) -> list[Belief]: ...
    def save_belief(self, b: Belief) -> None: ...
    def save_decision(self, d: Decision) -> None: ...
    def get_decision(self, decision_id: str) -> Decision | None: ...
    def save_experiment(self, e: Experiment) -> None: ...
    def save_action(self, a: Action) -> None: ...
    def save_outcome(self, o: Outcome) -> None: ...
    def save_prediction(self, p: PredictionEntry) -> None: ...
    def get_open_predictions(self, project_id: str) -> list[PredictionEntry]: ...
    def resolve_prediction(self, prediction_id: str, outcome: bool) -> PredictionEntry: ...
    def save_project(self, p: Project) -> None: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def save_objective(self, o: Objective) -> None: ...
    def save_founder_profile(self, f: FounderProfile) -> None: ...
    def save_financial_snapshot(self, fs: FinancialSnapshot) -> None: ...
    def save_company_case(self, c: CompanyCase) -> None: ...
    def save_memory(self, m: MemoryRecord) -> None: ...
    def get_rules(self, kind: RuleKind | None = None) -> list[Rule]: ...
    def save_rule(self, r: Rule) -> None: ...
    def append_event(self, ev: DomainEvent) -> None: ...
    def events_since(self, after_seq: int) -> list[DomainEvent]: ...
    def in_transaction(self, fn: Callable[[], None]) -> None: ...

# legacy/import_v10_2.py
class V10_2Importer:
    def scan(self) -> ImportManifest: ...
    def import_memory(self) -> ImportReport: ...
    def import_company_cases(self) -> ImportReport: ...
    def import_rules(self) -> ImportReport: ...
    def dry_run(self) -> ImportReport: ...
```

### 验收要点

- 所有域对象可被 pydantic 校验（`extra="forbid"`）；`python -c "from vencertia.domain import Evidence"` 通过。
- SQLiteRepository 全量 CRUD + 乐观锁（stale write 抛 `StaleWriteError`）+ 事务（失败回滚）测试通过。
- PostgresRepository：无 DSN 时实例化抛 `PostgresDisabledError`；有 DSN 时（CI optional）冒烟通过。
- 事件发布/订阅：EVIDENCE_ADDED 等 12 类事件可发布、可回放（`events_since`）。
- 导入工具：对示例 release 目录 `--dry-run` mapping 覆盖率 ≥ 95% 核心对象；幂等（跑两次不重复）。
- 既有 v0.1 `tests/` 中域相关测试语义可迁移（evidence/decision 行为在 T03 引擎测试中覆盖）。

---

## T03 — Runtime 确定性引擎全量（DECISION INTELLIGENCE）

**依赖**：T02

### 文件 `src/vencertia/runtime/`

| 文件 | 职责 |
|---|---|
| `evidence_policy.py` | `EvidencePolicy`：authority 层级表（9 级，版本化）、`grade()`/`apply_authority()`/`check_company_case_transferability()`、scope gate（COMPANY_CASE 隔离、LLM 降权）；依据 docs/evidence-policy.md |
| `belief_engine.py` | `BeliefEngine`：Beta-Bernoulli 伪计数更新（默认）或 Weighted Log-Odds（可切换）；uncertainty/confidence；conflict 检测；依据 docs/belief-engine.md |
| `uncertainty_engine.py` | `UncertaintyEngine`：`rank(decision, beliefs)` → `list[CriticalUncertainty]`（DecisionImpact×BeliefUncertainty 排序） |
| `decision_engine.py` | `DecisionEngine`：EU + 不确定性惩罚 + 不可逆成本 + 机会成本；margin/confidence；决策类型映射（GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION/ABSTAIN）；依据 docs/decision-engine.md |
| `convergence_engine.py` | `ConvergenceEngine`：7 态判定（NOT_CONVERGED/RESEARCH_MORE/EXPERIMENT_REQUIRED/SEARCH_EXHAUSTED/CONDITIONALLY_CONVERGED/CONVERGED/EXECUTE）；依据架构图 3.4 |
| `experiment_optimizer.py` | `ExperimentOptimizer`：评分 `EIG×DecisionImpact×Uncertainty÷Cost÷Time`；`propose()` 保证 ABSTAIN+next_experiment 同时输出；依据 docs/experiment-optimizer.md |
| `prediction_ledger.py` | `PredictionLedger`：`register(decision, beliefs)` 生成 PredictionEntry（belief_snapshot + context_snapshot_hash + policy_version）；`resolve(entry_id, outcome)` 结算；防事后篡改（快照校验） |
| `calibration_engine.py` | `CalibrationEngine`：Brier/ECE/buckets/分层（ALL/MODEL/DOMAIN/MODULE）；依据 docs/calibration.md |
| `opportunity_cost.py` | `OpportunityCostEngine`：`portfolio(user_id)` 计算各机会 expected_value/option_value/opportunity_cost/priority（opportunity_cost = 次优机会期望值） |
| `runtime.py` | `SolveOrchestrator`：`solve(request)` 全流程（compile→retrieve→research→evidence→belief→convergence→evaluate→experiment→structured answer）；`record_outcome(action_id, result)` 闭环（Outcome→Evidence→Belief→Decision→Prediction 结算→Calibration）；发布事件 |
| `context.py` | `ContextBuilder`：读投影（founder_profile/project_snapshot/critical_assumptions/top_evidence/latest_decisions/latest_experiments/conflict_alerts），供 capability 消费；不持久化 |

### 关键接口签名

```python
# runtime/evidence_policy.py
class EvidencePolicy:
    def grade(self, evidence: Evidence, policy: RuleSet | None = None) -> EvidenceGrade: ...
    def apply_authority(self, evidence: Evidence, policy_version: str) -> Evidence: ...
    def check_company_case_transferability(self, evidence: Evidence, project_context: dict) -> EvidenceGrade: ...
    def version(self) -> str: ...

# runtime/belief_engine.py
class BeliefEngine:
    def update(self, inp: BeliefUpdateInput) -> BeliefUpdateOutput: ...
    def uncertainty_of(self, belief: Belief) -> float: ...
    def prior_of(self, belief: Belief) -> float: ...

# runtime/decision_engine.py
class DecisionEngine:
    def evaluate(self, inp: DecisionEngineInput) -> DecisionEngineOutput: ...

# runtime/convergence_engine.py
class ConvergenceEngine:
    def check(self, decision: Decision, beliefs: list[Belief],
              critical: list[CriticalUncertainty]) -> ConvergenceReport: ...

# runtime/experiment_optimizer.py
class ExperimentOptimizer:
    def propose(self, inp: ExperimentProposalInput) -> ExperimentProposalOutput: ...
    def rank(self, experiments: list[Experiment], beliefs: list[Belief],
             critical_belief_id: str | None = None) -> list[RankedExperiment]: ...

# runtime/prediction_ledger.py
class PredictionLedger:
    def register(self, decision: Decision, beliefs: list[Belief]) -> list[PredictionEntry]: ...
    def resolve(self, entry_id: str, outcome: bool) -> PredictionEntry: ...
    def verify_snapshot(self, entry: PredictionEntry) -> bool: ...

# runtime/calibration_engine.py
class CalibrationEngine:
    def report(self, inp: CalibrationInput) -> CalibrationProfile: ...
    def update(self, inp: CalibrationInput) -> CalibrationProfile: ...

# runtime/runtime.py
class SolveOrchestrator:
    def __init__(self, repo: Repository, policy: EvidencePolicy, engines: EngineBundle,
                 model: ModelProvider, search: SearchProvider, bus: EventBus): ...
    def solve(self, request: SolveRequest) -> SolveResult: ...
    def record_outcome(self, action_id: str, result: str,
                       quantitative: dict | None = None,
                       outcome_type: OutcomeType = OutcomeType.PARTIAL) -> OutcomeRecordedResult: ...
    def evaluate_decision(self, decision_id: str) -> DecisionResult: ...
```

### 验收要点

- 引擎全部为纯函数/可注入（除 repo/bus），可单测。
- **行为回归**：v0.1 `test_evidence.py`/`test_experiments.py`/`test_decision.py` 语义断言迁移后全部通过（付款 > 模型推断、相关性折减、margin 门槛、ABSTAIN+实验）。
- 闭环测试：记录 outcome → 自动生成 evidence → belief 更新 → decision 再评估 → 收敛状态变化，事件链完整（OUTCOME_RECORDED → EVIDENCE_ADDED → BELIEF_UPDATED → DECISION_EVALUATED → PREDICTION_RESOLVED → CALIBRATION_UPDATED）。
- Prediction Ledger：注册后修改 belief 不影响快照；resolve 后 original probability 不可变；快照哈希校验可检测上下文篡改。
- Calibration：Brier/ECE 数值与手算样例一致；分层报告（MODEL/DOMAIN/MODULE）正确分组。
- Convergence：7 态转移在合成场景下符合状态机（架构 3.4）。
- Company Case 隔离：COMPANY_CASE 证据不通过 transferability 时不得改变项目 belief。

---

## T04 — Capability 骨架 + Providers（CAPABILITY 层，mock 实现）

**依赖**：T02

### 文件 `src/vencertia/providers/`

| 文件 | 职责 |
|---|---|
| `models.py` | `ModelProvider`（Protocol）：`generate_structured(task, schema, context) -> dict`、`complete(prompt) -> str`；`SearchProvider`（Protocol）：`search(query, k) -> list[SearchResult]`；`RetrievalProvider`（Protocol）：`retrieve(query, k) -> list[Document]`；`SearchResult{title,url,snippet,source,retrieved_at}`、`Document{id,content,metadata}` |
| `mock.py` | `MockProvider`：确定性输出（按 schema 返回占位/演示数据，无网络）；`MockSearchProvider`：返回内置文档；`MockRetrievalProvider`：按关键词返回内置文档 |
| `openai_compatible.py` | `OpenAICompatibleProvider`：httpx 调用 OpenAI-compatible 端点（`POST {base}/chat/completions`），`generate_structured` 用 `response_format=json_schema`（不支持时用 prompt 约束 + 解析兜底）；超时/重试 |
| `search.py` | `SearchAdapter` 骨架：将 `SearchProvider` 结果转换为候选 Evidence（authority=REVIEWED_EXTERNAL_RESEARCH 或 LLM_INFERENCE，未验证不得 VERIFIED） |

### 文件 `src/vencertia/capabilities/`

| 文件 | 职责 |
|---|---|
| `base.py` | `Capability`（Protocol）：`name`、`run(task, context_bundle) -> CapabilityResult`；`CapabilityResult{claims: list[Claim], evidence: list[Evidence], decision_skeleton: Decision | None, experiments: list[Experiment], notes}`；**所有输出为候选**，无写权 |
| `founder_diagnosis.py` | `FounderDiagnosisCapability`：从对话/记忆输出候选 FounderState 特征（evidence authority=FOUNDER_STATEMENT） |
| `market.py` | `MarketCapability`：市场/品类研究候选证据（REVIEWED_EXTERNAL_RESEARCH/MODEL_PRIOR） |
| `financial.py` | `FinancialCapability`：FinancialSnapshot 候选、unit economics 计算建议（SYSTEM_DERIVED 需人工确认） |
| `challenger.py` | `ChallengerCapability`：反假设/反驳证据候选（触发 conflict 检测） |
| `company_intelligence.py` | `CompanyIntelligenceCapability`：CompanyCase/ClaimTrace 检索与比较（遵守 Company Case 隔离；FundingRound 非需求证据） |
| `research.py` | `ResearchCapability`：研究规划 + 调用 SearchProvider → 候选 Evidence |
| `gtm.py` | `GtmCapability`：候选 DecisionOption/实验候选/行动规划（GTM 角度） |
| `__init__.py` | `build_capability_registry(settings) -> dict[str, Capability]`；`DecisionCompiler`（编译 Objective/Decision/Claim/Belief 候选）放 `capabilities/__init__.py` 或 `compiler.py` |

### 关键接口签名

```python
# providers/models.py
class ModelProvider(Protocol):
    def generate_structured(self, task: str, schema: dict, context: dict) -> dict: ...
    def complete(self, prompt: str) -> str: ...

# capabilities/base.py
class Capability(Protocol):
    name: str
    def run(self, task: str, context: ContextBundle) -> CapabilityResult: ...

# capabilities/__init__.py
class DecisionCompiler:
    def __init__(self, model: ModelProvider): ...
    def compile(self, problem: str, project_state: dict) -> CompiledDecision:
        # → Objective + Decision(含 options) + Claim[] + Belief[] 候选
```

### 验收要点

- 默认 `model_provider=mock` 时，系统离线可跑通 `solve`（不依赖任何外部 API）。
- `OpenAICompatibleProvider` 用 httpx mock（`respx`/monkeypatch）测试：请求格式、超时、json 解析；**无真实 key 也能通过测试**。
- capability 输出均为候选；直接调用不产生任何持久化副作用。
- Company Intelligence capability 的输出证据 scope=COMPANY_CASE，且不触发项目 belief 变更（除非人工 transferability）。
- 向量检索：只提供 `RetrievalProvider` 接口 + mock，**不接任何向量依赖**（ADR-006）。

---

## T05 — API/CLI + Benchmark + Demo + 文档 + 集成验证

**依赖**：T03, T04

### 文件（一）— API `src/vencertia/api.py`

FastAPI 全量端点（响应统一 `{code, data, message}`）：

| 方法 | 路径 | 职责 |
|---|---|---|
| GET | `/health` | 存活 + 版本 + policy_version |
| POST | `/v1/decisions/compile` | 编译决策（capability DecisionCompiler）→ Decision + Objective + Beliefs |
| POST | `/v1/decisions/evaluate` | 评估决策 → DecisionResult（含 ABSTAIN） |
| GET | `/v1/decisions/{id}` | 读取决策（含快照/历史） |
| POST | `/v1/evidence` | 新增证据（经 EvidencePolicy 校验赋权） |
| POST | `/v1/outcomes` | 记录 Outcome → 触发 belief→decision 闭环 |
| POST | `/v1/experiments/propose` | 实验推荐（未收敛时同时返回 ABSTAIN 状态） |
| POST | `/v1/experiments/{id}/resolve` | 实验结算（生成 EXPERIMENT_RESULT 证据） |
| POST | `/v1/predictions` | 创建 PredictionEntry（登记快照） |
| POST | `/v1/predictions/{id}/resolve` | 结算预测 |
| GET | `/v1/calibration` | 校准报告（支持 scope/key 参数） |
| GET | `/v1/projects/{id}/beliefs` | 项目 belief 列表 |
| GET | `/v1/projects/{id}/critical-uncertainties` | 决策关键不确定性排序 |
| POST | `/v1/solve` | 高级入口：compile→retrieve→research→evidence→belief→convergence→evaluate→experiment→结构化答案 |

```python
# 统一响应
class ApiResponse(BaseModel):
    code: int = 0
    data: dict | list | None = None
    message: str = "ok"

def create_app(settings: Settings, repo: Repository, runtime: SolveOrchestrator) -> FastAPI: ...
app = create_app(get_settings(), SQLiteRepository(get_settings().db_dsn), default_runtime())
```

### 文件（二）— CLI `src/vencertia/cli.py`

typer 全量命令：

| 命令 | 职责 |
|---|---|
| `vencertia solve <request.json>` | 高级入口（同 POST /v1/solve） |
| `vencertia decision compile <problem.json>` | 编译决策 |
| `vencertia decision evaluate <decision.json>` | 评估决策 |
| `vencertia evidence add <evidence.json>` | 新增证据 |
| `vencertia experiment propose <decision_id>` | 推荐实验 |
| `vencertia outcome record <action_id> <result>` | 记录 outcome |
| `vencertia prediction create <prediction.json>` | 创建预测 |
| `vencertia prediction resolve <id> <0\|1>` | 结算预测 |
| `vencertia calibration report [--scope MODEL] [--key gpt-4o]` | 校准报告 |
| `vencertia benchmark run --level L0\|L1 --path ...` | 运行基准 |
| `vencertia project beliefs <project_id>` | 项目 beliefs |
| `vencertia uncertainties <project_id>` | 关键不确定性 |
| `vencertia migrate-v10.2 --source <dir> [--dry-run]` | V10.2 导入 |
| `vencertia demo` | 演示场景（B2B SaaS） |

### 文件（三）— Benchmark `src/vencertia/benchmark/`

| 文件 | 职责 |
|---|---|
| `l0.py` | `L0Runner`：合成策略回归（保留 v0.1 24 例 `data/benchmarks/v0.2.jsonl`），断言决策行为不回归 |
| `l1.py` | `L1Runner`：历史 time-sliced 回放（`data/benchmarks/l1_cases.jsonl`）；**泄漏审计**：`leakage_audit_passed=true` 才准入；只喂 T0 信息 |
| `metrics.py` | 指标全量：`decision_accuracy`、`selective_accuracy`、`coverage`（abstention quality）、`brier`、`ece`、`experiment_selection_accuracy`、`critical_uncertainty_accuracy`、`evidence_precision_recall`、`decision_regret`；`compute_all(cases, predictions)` |

### 文件（四）— Demo 场景

| 文件 | 职责 |
|---|---|
| `examples/demo_b2b_saas_v1.json` | B2B SaaS MVP 6 周决策 + paid pilot 实验闭环：Objective/Decision（commit_mvp vs stop_project）/Beliefs（problem/wtp/access）/Evidence（访谈 + 0/4 付费试点）/Experiment 候选（paid concierge pilot 20 ICP、30 天） |
| `data/benchmarks/l1_cases.jsonl` | 5–10 条 L1 时间切片案例（合成，T0 信息 + future_outcome + leakage_audit_passed=true） |

### 文件（五）— 文档与交付

| 文件 | 职责 |
|---|---|
| `docs/api.md` | 14 端点请求/响应示例（含 SolveResult 结构） |
| `docs/cli.md` | 14 命令用法 |
| `docs/benchmark.md` | 基准分层/指标定义/准入流程/防泄漏纪律 |
| `docs/oss-admission-policy.md` | 从 oss-integration-decisions.md 升级为可执行策略（ADR-006） |
| `docs/implementation-report.template.md` | 每轮迭代报告模板（假设/基准切片/指标 delta/成本/失败模式/版本/回滚） |
| `docs/changelog.md` | 版本变更记录（v0.1 → v1.0） |
| `docs/architecture.md` 等 7 份设计文档 | 已由架构师交付（本批次） |
| `tests/`（T05 新增） | `test_api.py`（14 端点）、`test_cli.py`（14 命令）、`test_solve.py`、`test_benchmark_l0.py`、`test_benchmark_l1.py`、`test_e2e_demo.py`（demo 闭环端到端） |

### 关键接口签名

```python
# benchmark/metrics.py
def compute_decision_accuracy(predicted: list[str], gold: list[str]) -> float: ...
def compute_abstention_quality(decided: list[bool], correct: list[bool]) -> dict: ...
def compute_brier(preds: list[float], outcomes: list[int]) -> float: ...
def compute_ece(preds: list[float], outcomes: list[int], bins: int = 10) -> float: ...
def compute_experiment_selection_accuracy(predicted: list[str], gold: list[str]) -> float: ...
def compute_critical_uncertainty_accuracy(predicted: list[str], gold: list[str]) -> float: ...
def compute_evidence_precision_recall(hits: int, predicted: int, relevant: int) -> dict: ...
def compute_decision_regret(chosen: list[float], best: list[float]) -> float: ...

# benchmark/l1.py
class L1Runner:
    def __init__(self, runtime: SolveOrchestrator, repo: Repository): ...
    def run(self, path: str) -> L1Report:
        # 逐案例：只写 T0 信息 → 决策 → 与 reference 比较；outcome 只用于事后结算，不喂回 T0
```

### 验收要点

- API 14 端点全部有冒烟测试；`POST /v1/solve` 端到端返回含 decision+convergence+critical_uncertainties+next_experiment（未收敛时）。
- CLI 14 命令可运行；`vencertia demo` 输出：WTP 为关键不确定性、paid concierge pilot 为推荐实验、决策为 ABSTAIN/CONDITIONAL_GO。
- L0 基准 24/24 通过（行为不回归）；L1 案例 leakage_audit 检查：`leakage_audit_passed=false` 案例被拒绝。
- `make install && make verify` 全绿；`make api` 可启动。
- Demo 闭环演示：运行 outcome record（paid pilot 结果）→ beliefs 更新 → 决策收敛状态变化（演示 3.2 闭环）。
- 文档齐全：README/API/CLI/BENCHMARK/OSS_ADMISSION_POLICY/IMPLEMENTATION_REPORT 模板/CHANGELOG 均存在且与实现一致。

---

## 9. 共享知识（工程师必须遵守）

1. **响应/错误**：API 统一 `{code, data, message}`；域错误 → code 非 0；`StaleWriteError` → 409；`EntityNotFoundError` → 404。
2. **时间**：一律 UTC `datetime`（`utcnow()` helper）。
3. **ID 前缀**：`CLM_`/`E_`/`BLF_`/`DEC_`/`EXP_`/`ACT_`/`OUT_`/`PRD_`/`PRJ_`/`OBJ_`/`FS_`/`CMP_`/`M_`/`EV_`。
4. **状态变更**：capability 无写权；一切变更经 SolveOrchestrator/领域 Service + Repository（乐观锁 + 事件日志）。
5. **Evidence 不可变**：修正 = SUPERSEDE 新记录，不覆盖。
6. **LLM 输出**：默认 authority=MODEL_PRIOR/LLM_INFERENCE；未验证不得 VERIFIED。
7. **Company Case 隔离**：scope=COMPANY_CASE 证据不得直接更新项目 WTP；transferability ≥ 0.6 + 评审确认。
8. **Policy 版本**：PredictionEntry 记录 `policy_version`；authority 表版本 bump 时旧快照仍可解释。
9. **基准纪律**：L1 案例 `leakage_audit_passed=true`；冻结测试集不优化；新 OSS 必须过基准（ADR-006）。
10. **依赖纪律**：不新增 pyproject 依赖（除非 TASK 明确）；向量检索只留接口。

## 10. 交付节奏（3 轮工程迭代）

| 轮次 | 目标 | 内容 | 退出标准 |
|---|---|---|---|
| 迭代 1（T01→T02→T03 主体） | "内核可跑" | 基础设施 + 域模型 + SQLite 持久层 + 核心引擎（evidence/belief/decision/experiment/convergence） | `make test` 全绿；L0 24/24；`solve` 可在 mock 下给出 ABSTAIN+实验 |
| 迭代 2（T04→T05） | "接口可交付" | capabilities mock + providers + API 全量 + CLI 全量 + L1 harness + demo | 14 端点/14 命令测试通过；demo 闭环演示；L1 防泄漏检查通过 |
| 迭代 3（打磨/审计） | "质量与文档" | 乐观锁/事件审计复查、calibration 分层、迁移导入、文档一致性、IMPLEMENTATION_REPORT 填写 | `make verify` 全绿；文档与实现一致；回滚路径明确 |

> 每轮结束按 `docs/implementation-report.template.md` 记录：假设 / 基准切片 / 指标 delta / 成本 / 失败模式 / 版本 / 回滚。

---

## 11. 与 v0.1 的继承清单（实现时参考）

| v0.1 文件 | v1.0 目标 | 操作 |
|---|---|---|
| `domain.py` | `domain/` 包 | 重写拆分（保留 Belief/Evidence/Decision/Experiment/Prediction 语义） |
| `evidence.py` | `runtime/evidence_policy.py` + `runtime/belief_engine.py` | 升级（authority 表 + scope gate + conflict） |
| `decision.py` | `runtime/decision_engine.py` | 升级（DecisionType 7 值 + convergence 输出） |
| `experiments.py` | `runtime/experiment_optimizer.py` | 升级（propose 契约 + 分离） |
| `calibration.py` | `runtime/calibration_engine.py` | 保留 + 分层扩展 |
| `store.py` | `repositories/` | 重写（repository 模式 + 乐观锁 + migrations） |
| `runtime.py` | `runtime/runtime.py` | 重写（SolveOrchestrator + 事件） |
| `api.py` | `api.py` | 重写（14 端点） |
| `cli.py` | `cli.py` | 重写（14 命令） |
| `benchmark.py` | `benchmark/l0.py` + `metrics.py` | 重写（L0/L1/metrics 分离） |
| `integrations/base.py` | `providers/` | 升级（Model/Search/Retrieval 协议） |
| `examples/demo_saas_solve.json` | `examples/demo_b2b_saas_v1.json` | 扩展为闭环场景 |
| `data/benchmarks/v0.2.jsonl` | 保留 | L0 回归基线 |
