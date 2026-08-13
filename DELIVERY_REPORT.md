# Vencertia Intelligence Lab — delivery report

## Delivered

A runnable v0.1 decision-control kernel that replaces the AgentV9 multi-agent center of gravity with a calibration-first runtime.

Core loop:

`Decision → Beliefs → Evidence → Convergence check → (decide | experiment) → Outcome → Calibration`

The package contains:
- executable Pydantic domain contracts;
- deterministic Evidence Engine with provenance and correlation discounting;
- Belief update and uncertainty;
- Decision Engine with risk, irreversible cost, opportunity cost and abstention;
- Experiment Optimizer targeted at decision-critical uncertainty;
- Prediction Ledger persistence plus Brier/ECE calibration;
- FastAPI and CLI interfaces;
- L0 benchmark harness and 24 synthetic policy-regression cases;
- historical-case schema/template for the real benchmark;
- migration map from all AgentV9 roles to the new architecture;
- OSS integration admission policy.

## Verification at delivery

- pytest: all tests passing.
- L0 decision regression: 24/24.
- selective decision accuracy on L0: 100%.
- experiment selection on L0 abstentions: 100%.
- demo behavior: evidence remains insufficient for a six-week MVP commitment; WTP is detected as the critical uncertainty; paid concierge pilot is selected as the next experiment.

## What is intentionally not claimed

The synthetic benchmark does not demonstrate that Vencertia makes superior real startup decisions. Real calibration requires time-sliced historical cases and prospective predictions resolved against later outcomes. The repository includes the schema and operational path to collect that evidence.

## OSS decisions

Use external projects as replaceable adapters, not the domain core:
- LiteLLM: model gateway candidate.
- LangGraph: optional durable workflow runtime.
- Ragas: component-evaluation toolkit.
- DSPy: later optimization of structured inference modules.
- GPT Researcher: research-pipeline candidate, with outputs converted to Evidence rather than accepted as truth.
- Qdrant: only when benchmarked retrieval needs exceed simpler storage.
- PyMC: later hierarchical calibration after enough outcomes exist.

## Immediate production sequence

1. Populate 100–200 leakage-audited historical cases using `data/templates/historical_case_template.json`.
2. Freeze train/dev/test splits.
3. Implement the natural-language Decision Compiler behind `ReasoningProvider` and benchmark schema validity + critical-variable recall.
4. Implement Research→Evidence and benchmark evidence precision/recall and contradiction recall.
5. Start prospective Prediction Ledger collection from day one.
6. Add LiteLLM/LangGraph/Ragas only behind adapter boundaries and retain only measured improvements.
7. Introduce DSPy/Qdrant/PyMC only after the corresponding data/benchmark gate is met.

---

# v1.1 Delivery Report — Intelligence Ingestion

## Delivered (v1.1, incremental)

v1.1 closes the v1.0 gap where research evidence never reached the judgment loop:

- **Claim Binding pipeline** (ADR-008): research evidence → claim binding →
  belief chain; `UNBOUND_EVIDENCE` explicit; Claim Binding Accuracy data source.
- **Provider Composition Root** (ADR-009): `MODEL_PROVIDER` really decides the
  runtime provider; API/CLI share `build_container()`; provider failures are
  structured + retried (ADR-012).
- **Decision-relevant context** (ADR-010): 15 context classes + 10-dimension
  deterministic ranking.
- **Research with boundaries** (ADR-011): ResearchPlanner + ResearchStopRule
  (8 signals → SEARCH_EXHAUSTED / EXPERIMENT_REQUIRED).
- **Reliability**: dedup / conflict / freshness / BeliefUpdateRecord +
  posterior_version / DecisionTrace + Sensitivity / ConfidenceCalibrator
  (UNCALIBRATED honesty) / experiment criteria enforcement / prediction correct.
- **Evaluability**: L0 36/36 (26 v1.0 + 10 capability), L1 +5 metrics (N/A),
  L2 prospective registry, OSS admission experiment, CallRecorder observability,
  ruff + CI, docs merged, release zip.

## Verification at delivery (v1.1)

- pytest: **245 passed / 1 skipped** (v1.0 174 not regressed).
- L0: **36/36**; legacy reference 20/24 (unchanged, honestly reported).
- L1: 6/6 (+1 leakage rejected); v1.1 metrics N/A (no labeled data yet — not faked).
- ruff: All checks passed.
- demo: closed loop (40 events).
- CLI/API import: OK.

## Verification at delivery (v1.1.1 RC hardening)

- pytest: **417 passed / 0 skipped**（v1.1.2 Runtime Integrity Hardening 最终回归；v1.0 174 / v1.1-pre-RC 283 / v1.1-RC 391 零回归）。
- L0: **36/36**; legacy reference 20/24 (unchanged, honestly reported).
- L1: **6/6**（l1-07-leak 被 leakage gate 拒绝）.
- Synthetic Claim Binding Benchmark（GAP-04，34 cases / 14 类）:
  Precision 1.0 / Recall 0.96 / F1 0.9796 / Unbound 1.0 / Ambiguous 1.0 /
  Rejected 1.0 / Multi-Exact 0.75 / Multi-Partial 0.25 / Coverage 1.0
  （**Synthetic，非真实世界准确率**；CB-034 已知局限已标记）。
- L1 三层契约（GAP-05）：template→schema→model_validate→L1Runner 全链通过；
  leakage_audit_passed != true 的 case 拒绝执行正式 L1 benchmark。
- 三 Provider adapter PASS：mock / openai_compatible（构造）/ http
  （httpx MockTransport 10 种失败模式）。
- legacy V10.2 compat PASS；API/CLI smoke PASS；ruff 0 error。
- 版本：1.1.2（禁止 1.2.0）。

## What is intentionally not claimed (v1.1)

- Real Web Search / LLM are not called: mock default; `openai_compatible` is
  construction-tested only; live provider needs credentials.
- **Generic HTTP Search adapter implemented. No commercial search vendor is
  bundled. Live use requires user-supplied endpoint and credentials**
  （GAP-10，未集成任何商业搜索服务）。
- L1 v1.1 metrics (Claim Binding Accuracy / Research Efficiency / Evidence Yield /
  Belief Delta Quality / Decision Change Precision) are N/A until labeled or
  prospective data accumulates.
- Semantic rankers/matchers are protocol-only (no vector DB dependency).

---

# v1.2 Delivery Report — Semantic Protocols

## Delivered (v1.2, incremental)

- **M0 hardening（5 项）**：PG 后端 DSN 门控（`PostgresDisabledError`）、
  乐观锁单写入口、错误信封统一、prediction 单持久化点、审计留痕。
- **V-1 provenance/calibration**：`ModelParameter`（LLM 提议≠批准，PROPOSED/APPROVED
  语义）+ `ProvenanceType`；`Belief` 携带 `estimate_type` / `calibration_status`。
- **V-2 Decision Ledger**：`DecisionRecord`（推荐→行动→结果）+ `DecisionOutcomeRecord`
  持久化，`status=RECOMMENDED` + `abstain_reason`。
- **V-3 Model Critic**：`ModelCritique`（`ModelRisk`/`CritiqueFindingType` 结构化审查）+
  `ModelCriticGate.should_require` 纯字符串序值门控；`ChallengerCapability` 产出结构化 critique。
- **V-4 Stakes / 自适应 ABSTAIN**：`StakesClass`（LOW/MEDIUM/HIGH）三档阈值
  （`Settings.stakes_thresholds`），默认 MEDIUM 精确复现 v1.1.2 全局带。
- **V-5 Utility 关系类型**：`UtilityComponent` + `UtilityRelationType`
  （ADDITIVE/THRESHOLD/AND_GATE），非线性能利用关系。

## Verification at delivery (v1.2)

- pytest：**483 passed / 1 skipped / 0 failed**；ruff 0 error。

---

# v1.2.1 Delivery Report — BeliefEdge + ActionState + critic gate + PG CI

## Delivered (v1.2.1, incremental)

- **V-6 BeliefEdge 因果图**：9 类 `BeliefRelationType` + `BeliefEdge`
  （generic `entities` 表，无新迁移）；`Evidence.shared_signal_group` +
  `EvidenceApplication.signal_discount` 跨信念共享信号防 double counting
  （独立于 `dedup_discount`）。
- **V-7 ActionState + mode + 5 段投影**：展示层 `ActionState`
  （ACT/TEST/HOLD/WAIT/STOP）与引擎 `DecisionType` 双词表并存；
  `SolveRequest.mode`（EXPLORE/OPERATE）；`DecisionOption.option_kind`；
  `/v1/solve` Default（5 段合同）/ Advanced（`?advanced=true`）两层投影。
- **critic gate solve 接线**：solve 主链路在 decision 评估前按
  `ModelCriticGate.should_require` 跑 ChallengerCapability，`ModelCritique`
  附入 `SolveResultV11`；失败/None 降级放行（warn + `PROVIDER_FAILED`，永不阻塞）。
- **PG CI（Release Gate I）**：`ci.yml` 起 `postgres:16` service +
  `VENCERTIA_PG_DSN`，`pip install -e ".[postgres,dev]"`，真跑
  `test_postgres_parity.py`；`test_m05_postgres_repository_disabled_without_dsn`
  改为 hermetic（`monkeypatch.delenv` + `get_settings.cache_clear()`），
  本机（无 DSN）与 CI（有 DSN）双环境皆绿。

## Verification at delivery (v1.2.1)

- pytest：**506 passed / 1 skipped / 0 failed**（483 基线 + 23 新增，零回归）。
- ruff：0 error。
- 版本号：`__version__ = "1.2.1"`（`__api_contract_version__ = "1.2"` 不动）；
  `pyproject.toml` version 同步 1.2.1。
- PG parity：**诚实声明** —— 本机无 PostgreSQL/docker，`test_postgres_parity.py`
  维持 skip；Release Gate I 由 CI（`postgres:16` service）兑现。

---

# v1.3 Delivery Report — 展示层投影（默认 5 段合同）

## Delivered (v1.3, incremental)

- **展示层归位雏形**：`runtime/presentation.py` 集中中文文案映射 + 纯函数模板
  （`ACTION_STATE_ZH`/`DECISION_TYPE_ZH`/`PROVENANCE_ZH`/`BELIEF_RELATION_ZH` 等），
  引擎层不新增中文常量。
- **默认 5 段合同**：`solve_summary(result)` 输出 `current_judgment` / `rationale` /
  `biggest_unknown` / `next_step` / `change_condition` 五段 + ABSTAIN 四要素 +
  透明度段（belief graph / parameter provenance）。
- **概率文案与状态词表**：`probability_level` 概率带（Low/Moderate/High）、
  `estimate_phrase` 校准置信措辞、`localize_error_message` 异常中文化。
- **`/v1/solve` 双层投影**：`view=summary`（5 段合同）/ `advanced=true`（展开
  `SolveResultAdvancedView`）/ 默认 `full` 逐字节不变。

## Verification at delivery (v1.3)

- pytest：**532 passed / 1 skipped / 0 failed**（506 基线 + 26 新增，零回归）。
- ruff：0 error。

---

# v1.4 Delivery Report — 实验 VOI + 个性化 + 校准复盘 + 证据导入 + 快速求解

## Delivered (v1.4, incremental)

- **P1-1 实验 VOI 投影**：`experiment_voi_summary` 输出 `decision_change_condition`
  （成功/失败/模糊三态）+ `stop_rule` + 低决策影响实验降级标注。
- **P1-3 个性化投影**：`personalization_summary` 读取 StakesProfile，输出风险偏好
  中文档案（风险厌恶/中性/偏好）+ stakes_class 词表。
- **P1-5 校准复盘**：`calibration_summary` 拆分 forecast_calibration（Brier/ECE）
  与 decision_performance（regret 诚实标 N/A）；CLI `calibration report` 中文输出。
- **P1-2 证据批量导入**：`/v1/evidence/import` + `EvidenceImporter.import_batch`
  完整走 Candidate→Validation→持久化（dedup → 幂等 → grade → apply_authority → 入库）。
- **P1-4 快速求解**：`quick-solve` CLI 命令 + `run_quick_solve`（InMemory 一次性
  端到端，`lightweight=True` 轻量模式）。

## Verification at delivery (v1.4)

- pytest：**559 passed / 1 skipped / 0 failed**（532 基线 + 27 新增，零回归）。
- ruff：0 error。

---

# v1.5 Delivery Report — 结构性重构（零行为变更）

## Delivered (v1.5, refactor)

- **T01 引擎 DRY 收敛**：authority 权重表收敛到 `evidence_policy.AUTHORITY_TABLE`
  单一来源（各调用点保留各自 fallback：`context.py=0.0`，其余 `=0.1`）；校准
  bins/piecewise 收敛到 `CalibrationEngine`（`ConfidenceCalibrator` 委托）；死条件
  清理；`__import__("math")` 内联改顶部 `import math`。
- **T02 展示层归位**：`runtime/presentation.py` 迁移到独立 `vencertia.presentation`
  包；`runtime/presentation.py` 保留 deprecated re-export shim（既有 import 零破坏）；
  解除 `runtime.py` 反向 import 展示常量的边界渗漏。
- **T03 测试 helper 抽提**：`_orchestrator`/`_client`/`FIVE_KEYS` 复制粘贴收敛到
  `tests/conftest.py` 共享 fixture/常量。
- **T04 版本 + 文档漂移修复**：`__version__ = "1.5.0"`（`__api_contract_version__`
  维持 `"1.4"`，无 API 契约变更）；README/DELIVERY/iteration-log 补齐 v1.3/v1.4 段。

## Verification at delivery (v1.5)

- pytest：**559 passed / 1 skipped / 0 failed**（零回归，重构不改行为）。
- ruff：0 error。


