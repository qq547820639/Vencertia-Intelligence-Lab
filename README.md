# Vencertia Adaptive Decision System v1.2.1

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
make test             # pytest（506 passed / 1 skipped）—— v1.2.1 V-6/V-7 + critic gate + PG CI 最终回归
make demo             # B2B SaaS MVP 6 周决策闭环演示
make benchmark        # L0 基准（36/36）+ legacy 参考
make benchmark-binding  # Synthetic Claim Binding Benchmark（GAP-04，独立）
make benchmark-all    # L0 + Binding
make lint             # ruff check（0 error）
make ci               # lint → test → benchmark → API/CLI smoke
make api              # FastAPI: http://localhost:8000
make verify           # test + benchmark + import 检查
make release          # 打包 Vencertia_Intelligence_Lab_v1.1.2.zip
```

> 测试数字为 v1.2.1 最后一次干净回归（1 skipped 为 PostgreSQL parity，本机无 PG 由 CI 兑现）；历史数字对照见
> `docs/baseline-v1-0.md`（v1.0 174 / v1.1-pre-RC 283 / v1.1-RC 345 / v1.1.2 417 / v1.2 483 / v1.2.1 506，各状态不混数字）。

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
