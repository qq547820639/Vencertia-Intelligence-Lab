# Vencertia Adaptive Decision System v1.0

> 一个"校准优先"的决策运行时：在高度不确定的创业语境中，把"该不该做"变成
> 有据可依的判断——并在证据不足时诚实地告诉你"现在还下不了结论"（ABSTAIN）。

Vencertia 不是 Prompt-driven Multi-Agent 顾问，而是一个 **Decision Runtime**：
确定性引擎拥有状态变更权，LLM/能力模块只是候选产出者（无写权）。
三层分离：**REALITY**（canonical truth，Repository 独占写）→
**DECISION INTELLIGENCE**（可解释、可追溯、可校准的确定性引擎）→
**CAPABILITY**（外部智能，可替换适配器）。

---

## 快速开始

```bash
make install          # pip install -e ".[dev]"
make test             # pytest（124 passed）
make demo             # B2B SaaS MVP 6 周决策闭环演示
make benchmark        # L0 基准（26/26）+ legacy 参考
make api              # FastAPI: http://localhost:8000
make verify           # test + benchmark + import 检查
```

CLI 也可直接使用：

```bash
PYTHONPATH=src python -m vencertia.cli demo
PYTHONPATH=src python -m vencertia.cli benchmark run --level L0
PYTHONPATH=src python -m vencertia.cli migrate-v10.2 --source legacy/... --dry-run
```

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/architecture.md` | 三层架构 + Mermaid 图 + 权力边界 + 不变式 |
| `docs/domain-model.md` | 域对象字段级定义（权威） |
| `docs/{decision,belief,evidence-policy,experiment-optimizer,calibration}-engine.md` | 引擎算法 |
| `docs/architecture-decisions.md` | ADR-001~007 |
| `docs/migration-v10.2-to-decision-runtime.md` | V10.2 映射 |
| `docs/api.md` / `docs/cli.md` | 接口文档 |
| `docs/benchmark.md` | 基准分层/指标/防泄漏 |
| `docs/oss-admission-policy.md` | OSS/模型准入策略 |
| `docs/iteration-log.md` | 3 轮迭代记录 |
| `TASK_BREAKDOWN.md` | 工程师施工图 |

## v1.0 与 v0.1 差异

- 域模型从单文件拆分为 `domain/` 包（Objective/Claim/Evidence/Belief/Decision/
  Experiment/Prediction/Calibration/Founder/Memory/CompanyCase/Policy…全量 pydantic v2）。
- 证据权威从 SOURCE_PRIOR 升级为 9 级 AuthorityHierarchy + scope gate
  （Company Case 隔离、LLM 降权、transferability）。
- 决策类型显式化（GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION/ABSTAIN）；
  ABSTAIN 必带 next_experiment。
- 新增收敛状态机（7 态）、Prediction Ledger（快照防篡改）、校准分层
  （ALL/MODEL/DOMAIN/MODULE）、乐观锁持久层、事件日志、V10.2 导入工具、
  L0/L1 基准 + 防泄漏审计。

## 边界与假设

- 默认 `model_provider=mock`：系统离线可跑（不依赖任何外部 API）。
- PostgreSQL 为可选后端（`VENCERTIA_PG_DSN` 门控）。
- v1.0 单用户假设；Company Case 数据源以 adapter 接口 + mock 交付。
