# Vencertia v1.7 实施计划（Model Critic 投影深化）

> 日期：2026-08-14
> 输入：V11 蓝图 §3.8（Model Critic / Unknown Unknowns Protocol）+ v1.4 PRD P2 池（Model Critic 投影）

## 0. 背景与裁决

`ModelCritique`（V-3）已在 runtime 层完整接线——`SolveResultV11.model_critique` 字段 + `_run_model_critic()`（HIGH stakes 触发，失败降级不阻塞）。但 presentation 层的 `solve_summary` 从未投影它：用户在 CLI `solve` 默认 5 段合同里**看不到模型挑战结果**，这违背 V11 蓝图"Model Critic 能挑战模型本身、用户应知晓模型风险"的意图，也是 v1.4 PRD 留档的 P2 缺口。

本轮（v1.7）补齐这最后一块 UX 盲区。版本 **1.7.0**（`__api_contract_version__` 维持 1.4——纯展示层新增，API 契约零变化）。

## 1. 任务清单

### T1 — presentation 层新增 critique 中文投影
1. `presentation/__init__.py` 新增映射常量：
   - `MODEL_RISK_ZH = {"LOW": "低", "MEDIUM": "中", "HIGH": "高"}`
   - `CRITIQUE_FINDING_ZH`（6 类 finding 中文）
2. 新增纯函数 `critique_summary(critique: ModelCritique | None) -> dict`：
   - 有 critique：投影 model_risk 中文、findings 中文列表、missing_variables/hidden_dependencies/regime_risks/double_counting 四类清单、recommendation、`model_risk_high` 布尔标记
   - 无 critique（None）：`{"available": False, "note": "未触发模型挑战（低/中风险决策默认跳过）"}`——键恒在，不省略
3. `solve_summary` 透明度段追加 `model_critique` 键（调用 critique_summary）。
4. `__all__` 补 2 个新常量 + 1 函数（19 → 22 名）；shim 同步。

### T2 — 测试 + 版本 + 文档
1. 新增 `tests/test_v17_critique.py`：critique_summary 有/无 critique 两分支 + solve_summary 接入 + 中文映射正确性。
2. 版本 1.7.0（`__init__.py` / `pyproject.toml` + 4 个测试文件版本断言同步 1.6.0→1.7.0）。
3. README 标题/测试数字刷新。

### T3 — CI 验证结论记录（如实声明）
在交付说明中记录：CI 配置自洽（postgres:16 + psycopg extra + 有 DSN 不 skip），但本机无 gh 认证/无 PG，PG parity 实际运行结果需由 push 触发 GitHub Actions 后确认——不伪造"已验证"。

## 2. 验收

1. `pytest tests/ -q` 560+新测试全绿；`ruff check src tests` 0 error。
2. `solve_summary(result)["model_critique"]` 键恒在；有 critique 时 `model_risk_zh`/`findings_zh` 非空。
3. 无 critique 时 `available=False` + 占位 note，不抛异常。
4. git 提交 + push origin main。
