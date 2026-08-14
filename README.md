# Vencertia Adaptive Decision System v2.0.0

> 一个"校准优先"的决策运行时：在高度不确定的创业语境中，把"该不该做"变成
> 有据可依的判断——并在证据不足时诚实地告诉你"现在还下不了结论"（ABSTAIN）。

Vencertia 不是 Prompt-driven Multi-Agent 顾问，而是一个 **Decision Runtime**：
确定性引擎拥有状态变更权，LLM/能力模块只是候选产出者（无写权）。
三层分离：**REALITY**（canonical truth，Repository 独占写）→
**DECISION INTELLIGENCE**（可解释、可追溯、可校准的确定性引擎）→
**CAPABILITY**（外部智能，可替换适配器）。

v1.1（Intelligence Ingestion）把研究证据真正接进判断闭环：Claim Binding 流水线、
决策相关上下文、Research Planner/Stop、Decision Sensitivity、可观测性与 L0-L2 基准。

---

## 快速开始

```bash
make install          # pip install -e ".[dev]"
make test             # pytest（621 passed / 9 skipped）—— v2.0.0 最终回归（想法→决策→BP 全路径）
make demo             # B2B SaaS MVP 6 周决策闭环演示
make benchmark        # L0 基准（36/36）+ legacy 参考
make benchmark-binding  # Synthetic Claim Binding Benchmark（GAP-04，独立）
make benchmark-all    # L0 + Binding
make lint             # ruff check（0 error）
make ci               # lint → test → benchmark → API/CLI smoke
make api              # FastAPI: http://localhost:8000
make verify           # test + benchmark + import 检查
make release          # 打包 Vencertia_Intelligence_Lab_v<__version__>.zip（版本号自动派生）
```

> 测试数字为 v2.0.0 最后一次干净回归（9 skipped 均为 PostgreSQL parity，本机无 PG 由 CI 兑现）；历史数字对照见
> `docs/baseline-v1-0.md`（v1.0 174 / v1.1-pre-RC 283 / v1.1-RC 345 / v1.1.2 417 / v1.2 483 / v1.2.1 506 / v1.3.0 532 / v1.4.0 559 / v1.5.0 559 / v1.6.0 560 / v1.7.0 565 / v1.8.0 569 / v1.9.0 597 / v1.9.1 611 / v2.0.0 621，各状态不混数字）。

CLI 也可直接使用：

```bash
PYTHONPATH=src python -m vencertia.cli demo
PYTHONPATH=src python -m vencertia.cli benchmark run --level L0
PYTHONPATH=src python -m vencertia.cli benchmark run --level CLAIM_BINDING
PYTHONPATH=src python -m vencertia.cli research plan <decision_id>
PYTHONPATH=src python -m vencertia.cli evidence bind <evidence_id>
PYTHONPATH=src python -m vencertia.cli decision sensitivity <decision_id>
PYTHONPATH=src python -m vencertia.cli belief history <belief_id>
```

## Web 决策工作台（v1.8 → v1.9 决策复盘器）

`make api` 后浏览器打开 **http://localhost:8000/** 即是零构建链的决策复盘器：
左侧「发起一个新决策」→ 得到默认 5 段合同（当前判断 / 为什么 / 最大未知 / 下一步 /
什么会改变判断），右侧「校准仪表盘 + 决策台账」追踪你的判断准不准。
v1.9 补上复盘闭环：待复盘预测可一键「成真/落空」结算并实时刷新命中率/ECE/布赖尔分；
最近 10 条判断保存在浏览器本地（localStorage）可回看；判断耗时可见。
无需安装 Node，前端直接复用后端已计算好的中文投影层。

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/architecture.md` | 三层架构 + Mermaid 图 + 权力边界 + 不变式（含 v1.1 节） |
| `docs/v1.1-design.md` | v1.1 增量架构设计（1086 行，权威） |
| `docs/architecture-decisions-next.md` | ADR-008~012 |
| `docs/domain-model.md` | 域对象字段级定义（权威，小写连字符 canonical） |
| `docs/intelligence-ingestion.md` | 智能摄取总览（v1.1） |
| `docs/claim-binding.md` | Claim Binding 流水线（v1.1） |
| `docs/research-runtime.md` | Research Planner/Stop（v1.1） |
| `docs/evidence-pipeline.md` | dedup / conflict / freshness（v1.1） |
| `docs/belief-update-trace.md` | BeliefUpdateRecord + 版本化（v1.1） |
| `docs/decision-sensitivity.md` | DecisionTrace / Sensitivity（v1.1） |
| `docs/providers.md` | Provider Composition Root + 韧性（v1.1） |
| `docs/{decision,belief,evidence-policy,experiment-optimizer,calibration}-engine.md` | 引擎算法 |
| `docs/architecture-decisions.md` | ADR-001~007 |
| `docs/migration-v10.2-to-decision-runtime.md` | V10.2 映射 |
| `docs/api.md` / `docs/cli.md` | 接口文档 |
| `docs/benchmark.md` | 基准分层/指标/防泄漏 |
| `docs/oss-admission-policy.md` | OSS/模型准入策略 |
| `docs/iteration-log.md` | v1.0 + v1.1 迭代记录 |
| `docs/implementation-report-next.md` | v1.1 交付报告 |
| `docs/v1.2-construction-plan.md` | v1.2 施工图（M0 + V-1~V-5） |
| `docs/implementation-plan-v12-2026-08-13.md` | v1.2 实施计划（范围/裁决） |
| `docs/agentv11-v112-mapping-review.md` | AgentV11 → v1.1.2 映射评审（V-6/V-7 落地建议） |
| `docs/v1.1.2-code-walkthrough-review.md` | v1.1.2 代码走查评审 |
| `TASK_BREAKDOWN.md` / `TASK_BREAKDOWN_NEXT.md` | 工程师施工图 |

## v1.1 与 v1.0 差异

- **Claim Binding**：研究证据 → Claim → Belief 可追溯；`UNBOUND_EVIDENCE` 显式留痕；
  Claim Binding Accuracy 有了唯一数据源。
- **Provider Composition Root**：`MODEL_PROVIDER` 环境变量真实决定运行时 Provider；
  API/CLI 共用 `build_container()`；Provider 失败结构化 + 重试。
- **决策相关上下文**：15 类上下文 + 10 维排序（deterministic/lexical 基线）。
- **Research 有边界**：ResearchPlanner 按 critical impact 排序 + ResearchStopRule
  8 类信号 → SEARCH_EXHAUSTED / EXPERIMENT_REQUIRED。
- **决策敏感度**：DecisionTrace + DecisionSensitivity（翻转阈值 + STRONG/FRAGILE）。
- **可靠性**：Evidence dedup / conflict / freshness；BeliefUpdateRecord + posterior_version。
- **可评估性**：L0 +10 能力用例（36/36）；L1 +5 指标（N/A 语义）；L2 prospective registry；
  OSS admission experiment；CallRecorder 可观测性；ruff + CI。

## 边界与假设

- 默认 `model_provider=mock`：系统离线可跑（不依赖任何外部 API）。
- PostgreSQL 为可选后端（`VENCERTIA_PG_DSN` 门控）。
- 真实 Web Search/LLM 未配置时如实声明（"Adapter implemented, live provider
  unavailable without credentials"）；数据不足标 N/A，不伪造。

## v1.2 / v1.2.1 差异

- **v1.2 语义协议（M0 + V-1~V-5）**：M0 止血 5 项；V-1 provenance/calibration
  （`ModelParameter` 提议≠批准）；V-2 Decision Ledger（`DecisionRecord` →
  `DecisionOutcomeRecord` 推荐→行动→结果）；V-3 Model Critic（`ModelCritique`
  结构化审查）；V-4 Stakes 三档自适应 ABSTAIN（`StakesClass`）；V-5 Utility
  关系类型（`UtilityRelationType`）。
- **V-6 BeliefEdge 因果图**：9 类 `BeliefRelationType` 声明式信念关系 +
  `Evidence.shared_signal_group` 跨信念共享信号防 double counting（独立于
  `dedup_discount`）。
- **V-7 ActionState + mode**：展示层 `ActionState`（ACT/TEST/HOLD/WAIT/STOP）
  与引擎 `DecisionType` 双词表并存；`SolveRequest.mode`（EXPLORE/OPERATE）；
  `/v1/solve` Default（5 段合同）/ Advanced（`?advanced=true` 展开
  `SolveResultAdvancedView`）两层投影。
- **critic gate 接线**：solve 主链路按 `ModelCriticGate.should_require` 在
  decision 评估前跑 ChallengerCapability，`ModelCritique` 附入 SolveResult；
  失败/None 一律降级放行，永不阻塞决策。
- **PG CI（Release Gate I）**：`.github/workflows/ci.yml` 起 `postgres:16`
  service + `VENCERTIA_PG_DSN`，`pip install -e ".[postgres,dev]"`，真跑
  `test_postgres_parity.py`（本机无 PG 时该测试诚实 skip，由 CI 兑现）。

## v1.9 差异

- **代码质量批次（5 P0 / 14 P1 全修）**：L2 registry 一行一条 upsert + 跟踪文件清零；
  L0/L1 无 gold/无 T0 决策诚实失败；`list_bindings` `use_enum_values` 崩溃修复；
  PG stale-write 事务泄漏 + 三后端 create-version 统一；乐观锁 `+1` 约定回写修复；
  `make_release` 版本号从 `__version__` 派生（不再漂移）；`openai_compatible` kind-tag
  误当 JSON Schema 修复 + `complete()` 纯文本回退；工厂重试只重试 transient 错误；
  EventBus 逐 handler 异常隔离；`api.py` 模块级 `app` 惰性化（import 零副作用）；
  `call_recorder` 缓存；`VENCERTIA_STAKES_THRESHOLDS`/`VENCERTIA_CRITIC_REQUIRED_STAKES`
  环境变量 + 解析失败告警；9 处字符串 `__import__` 全部清除。
- **UX 批次**：`/v1/review` 台账行带决策问题标题；Web 工作台补复盘闭环（预测
  成真/落空结算 + 会话历史 + 耗时 + 示例占位 + 错误态）；CLI `solve`/`quick-solve`
  默认输出 rich 中文面板（`--json` 保留机器可读）；设计令牌补全 `--on-accent`。
- **评审**：`CODE_ARCHITECTURE_REVIEW.md`（§1–§10 全量走读评审 + 历史对比）与
  `docs/implementation-plan-v19-2026-08-14.md`（本轮施工图，含 Round 2）。
- **v2.0**：`docs/implementation-plan-v20-2026-08-14.md`（想法→决策→BP 全路径 + Skill 层施工图）。
- **Round 2 技术债清理**：4 个 EventType 接真实生命周期点（实验执行/上下文失效审计）；
  L1 运行时 JSON-Schema 校验（schema-invalid 拒绝不执行，jsonschema 缺失优雅跳过）；
  `claim_binding` 未知 scope fail-loud；仓储 `close()`/上下文管理器；
  `make_release` 覆盖率产物排除；Web 工作台「展开完整模型」渐进披露
  （信念依赖中文关系 / 待确认参数 / 实验 VOI / 个性化 / 模型自检）。

## v1.9.1 差异

- **复盘闭环补全**：`POST /v1/decisions/{id}/act` —— 台账 RECOMMENDED→ACTED→SETTLED；
  带 `result` 即走既有 outcome 结算闭环（证据→信念→预测→校准→决策再评估→复盘记录）；
  `DECISION_ACTED` 事件留痕；Web 台账「标记行动 / 记录结果」内联表单。
- **校准曲线可视化**：仪表盘零依赖 SVG 可靠性图（置信度桶 vs 实际命中率 + 完美校准对角线），
  数字卡片之外的第一张图。
- **PG 行为级 parity 套件**：`tests/test_postgres_parity_behavior.py` 双后端参数化
  （CRUD/乐观锁/事务原子性/绑定与更新记录热表/事件日志回放），本机无 DSN 诚实 skip，
  CI `postgres:16` service 真实兑现。

## v2.0 差异（想法 → 决策 → 商业计划 全路径）

- **入口层**：`POST /v1/ideas/assess` —— 想法 → 决策问题 + 假设清单（模型提议，显式标注
  待确认）+ 最大未知 + 就绪的 solve 请求；CLI `vencertia idea`；Web「从想法开始」面板
  一键转入决策判断。
- **出口层**：`POST /v1/bp` —— 已持久化决策 → 七章商业计划（执行摘要/市场机会/为什么
  是我们/关键假设与风险/计划与里程碑/什么会推翻/复盘与校准）+ Markdown 全文；市场数据
  不足的章节诚实 N/A，不伪造；CLI `vencertia bp [--out]`；Web 台账「生成 BP」+「复制全文」。
- **Skill 层（V11 经验资产迁移）**：`vencertia/skills/` —— 5 个 legacy V11 专家提示词
  迁移为版本化 skill（market/financial/plan/founder/execution，谱系指向源 docx），
  输出走 pydantic 契约 + 引用校验门（数字必须有 source_claim_id，禁止无出处数据），
  编排路由按阶段调度；mock 模式确定性模板回退、真实 LLM 即插即用；
  `GET /v1/skills` 资产目录 + CLI `vencertia skills`。
- **定位**：规则拥有状态（脊椎），skill 承载经验（肌肉）——不是回到 prompt 驱动的旧路，
  也不是停在硬编码程序。详见 `docs/implementation-plan-v20-2026-08-14.md`。
