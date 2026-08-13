# Vencertia v1.2 迭代实施计划（M0 止血 + V-1~V-5 语义协议落地）

> 主理人：齐活林（Qi）· 日期：2026-08-13
> 输入：`docs/v1.1.2-code-walkthrough-review.md`（3 GAP + 5 P0）与 `docs/agentv11-v112-mapping-review.md`（12 项映射 + V-1~V-7 增量）
> 范围：本轮一次迭代执行完 **M0（5 项工程止血）+ V-1~V-5（V11 五组语义协议）**；V-6/V-7 后置（蓝图裁定 Core Correctness 先于体验深化）

## 0. 裁决说明

- 跳过 PM 阶段：需求已由两份审查报告精确定义（含文件路径/行号/接口建议），无需 PRD。
- 流程：架构师（增量施工图）→ 工程师（实现）→ QA（测试验证）→ 主理人汇总。
- 环境：本机无 pydantic，先建隔离 venv（`/Users/panhao/.workbuddy/binaries/python/envs/vencertia`）安装项目依赖，恢复 417 tests 基线后开工。

## 1. M0 工程止血（5 项，来源：v1.1.2 走读报告 §7）

| # | 问题 | 位置 | 修复方式 |
|---|---|---|---|
| M0-1 | 环境变量名漂移 | `config.py:167` vs 文档 | `Settings.from_env` 兼容 `MODEL_PROVIDER` 别名（优先 `VENCERTIA_MODEL_PROVIDER`，回退读 `MODEL_PROVIDER` 并告警），统一文档，加 `os.environ` 端到端测试 |
| M0-2 | `decision_sensitivity_signal` 恒 0 | `runtime.py:483-491`、`research_service.py:230-238` | 构造 RoundSummary 前跑 `decision_engine.evaluate` 取 before/after 差值，喂入信号；补非 0 断言测试 |
| M0-3 | API 错误两套格式 | `api.py` 错误路径全 `HTTPException(detail=)` | 注册统一 exception handler，把 EntityNotFound/StaleWrite/ValueError/ProviderError 映射为 `{code,data,message}` envelope（HTTP 状态码不变） |
| M0-4 | Prediction 双重写 + 字段缺失 | `prediction_ledger.py:69`、`runtime.py:1101-1106` | `register()` 不落库，统一由调用方落一次；API/CLI 创建时回填 domain/model_tag/module_tag（缺省 "default"） |
| M0-5 | PostgreSQL 路径未验证 | `migrations/__init__.py`、`test_v11_extra.py:163` | PG 迁移补 v1.1 专表（claim_bindings/belief_update_records）；写 PG parity 测试（无 PG 环境时 skip 标记）；本机验证受限则如实声明 |

## 2. V-1~V-5 语义协议（来源：agentv11 映射报告 §C）

| # | 协议 | 落地内容 | 关键文件 |
|---|---|---|---|
| V-1 | calibration_status 5 态 + EstimateType + 参数 provenance | 扩 `CalibrationStatus`（UNCALIBRATED/LOW_SAMPLE/DOMAIN_CALIBRATED/USER_CALIBRATED/VALIDATED）；`Belief` 加 `estimate_type`+`calibration_status`；`DecisionOption.belief_coefficients` 换 `ModelParameter(value,provenance,status,approved_by)`；LLM 编译产物默认 `LLM_PROPOSED/PROPOSED` | `domain/calibration.py`、`domain/belief.py`、`domain/model_parameter.py`（新）、`capabilities/__init__.py` |
| V-2 | Decision Ledger | `DecisionRecord`（recommendation/action_taken/model_version/abstain_reason）+ `OutcomeRecord`（regret_estimate/counterfactual_status）；solve 落地写 DecisionRecord；outcome 回填（不可识别标 NOT_IDENTIFIABLE） | `domain/decision_ledger.py`（新）、`runtime/runtime.py`、`outcome_settlement_service.py` |
| V-3 | Model Critic 结构化 | `ModelCritique`（missing_variables/hidden_dependencies/regime_risks/double_counting/model_risk）；ChallengerCapability 输出结构化 critique；高风险 solve 前 critic gate | `domain/critic.py`（新）、`capabilities/challenger.py` |
| V-4 | StakesProfile + Adaptive ABSTAIN | `StakesProfile` 8 维 + StakesClass；config 分层阈值带；`decision_engine.evaluate` 按 stakes_class 查阈值；ABSTAIN 输出带 deadline/exit/stop | `domain/stakes.py`（新）、`config.py`、`decision_engine.py` |
| V-5 | Utility 关系类型 | `UtilityComponent(relation_type,coefficient,threshold)`；`uncertainty_engine` 按 relation_type 执行（AND_GATE/THRESHOLD 先，MULTIPLICATIVE 次）；硬约束先于 Utility | `domain/utility.py`（新）、`uncertainty_engine.py` |

## 3. 执行顺序与验收

1. **环境**：venv + `pip install -e ".[dev]"`，跑基线 `pytest`（目标 417 passed / 0 skipped 或如实记录偏差）。
2. **架构师**：出增量施工图（文件清单/接口签名/依赖顺序/验收要点），落盘 `docs/v1.2-construction-plan.md`。
3. **工程师**：按施工图实现全部代码 + 新测试；自跑 pytest + ruff；全局一致性审查（IS_PASS: YES）。
4. **QA**：新增测试验证（M0 逐项回归 + V-1~V-5 语义行为）+ 全量回归；智能路由判定。
5. **主理人**：汇总交付清单与验证数字，更新 README/DELIVERY 文档。

## 4. 明确不做（本轮）

- 不重写 15 份 Prompt 为 7 层 Stack 文本；不扩 Explore 8 个 Specialist。
- V-6（BeliefEdge 因果图）/ V-7（ActionState 词表 + EXPLORE/OPERATE 模式）后置到下一迭代。
- 不改 legacy/agent_v11/ 归档内容。
