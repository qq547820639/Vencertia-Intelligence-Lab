# Vencertia v1.9 实施计划（代码质量 + UX 深化迭代）

> 日期：2026-08-14
> 基线：v1.8.0（HEAD 5749188e + 未提交的 v1.9 review-dashboard 工作区）
> 输入：全仓库系统性走读（根目录 → src 各层 → tests/docs/data）+ 3 路并行深读
> （providers/repositories、benchmark/legacy/scripts、domain/events/capabilities）+ `CODE_ARCHITECTURE_REVIEW.md` 续写。
> 授权：全权裁决，一次性迭代执行完。

---

## 0. 版本结论（走读印象）

代码层面的既定目标**已全部达成**：三层架构（REALITY → DECISION INTELLIGENCE → CAPABILITY）真实落地，
确定性引擎集（belief/uncertainty/decision/convergence/experiment/prediction/calibration + v1.1 智能摄取 +
v1.2 语义协议）完整、可解释、可校准；571 测试 + L0 36/36 + Claim Binding 33/34 全绿。
但**用户体验与工程卫生仍有明确可深化的空间**：UX 诊断报告（`docs/ux-diagnosis-2026-08-14.md`）的
15 项症状中若干项尚未落地；走读新发现 5 项 P0 / 14 项 P1 工程缺陷（乐观锁分叉、PG 事务泄漏、
L2 registry 数据完整性、OpenAI 适配器失效、版本漂移等）。

## 1. 任务清单（本轮一次性执行）

### T1 — P0 数据正确性（5 项）
- L2 registry 改一行一条 upsert（settle 原地改写，register 幂等）；`VENCERTIA_L2_REGISTRY_PATH`；
  跟踪文件清零（测试污染 326 行）。
- L2 文件写失败 logging 可见（不再静默）。
- L0 无 gold 约束案例诚实失败（不再虚高 pass_rate）。
- L1 `t0["decision"]` 缺失 → 诚实失败案例，不再 KeyError 中止整轮。
- `list_bindings` status 过滤 `use_enum_values` 崩溃修复。

### T2 — P1 可靠性/一致性（14 项）
- `make_release.py` VERSION 从 `__init__.py` 派生（修 v1.1.2 漂移 + `.coverage` 排除 + docstring）。
- `openai_compatible`：kind-tag ≠ JSON Schema 判别 + `json_object` 兜底；`complete()` 纯文本回退。
- PG stale-write 事务泄漏（`_rollback_implicit`，深度感知）；SQLite 同修。
- 三后端 create-with-expected_version 统一要求 version==1。
- `runtime.py` 机会成本回写走乐观锁 `+1` 约定。
- EventBus 逐 handler 异常隔离 + logging。
- `api.py` 模块级 `app` 惰性化（消除 import 副作用；`uvicorn vencertia.api:app` 不变）。
- `container.call_recorder` 属性缓存；空转 try/except 删除。
- 工厂重试仅重试 transient 错误（SchemaMismatch/InvalidJSON/Empty/Partial 立即失败）。
- `MockRetrievalProvider` 无匹配返回空（不再整库兜底）。
- `config`：`VENCERTIA_STAKES_THRESHOLDS`（JSON 合并）/`VENCERTIA_CRITIC_REQUIRED_STAKES` 环境变量；
  `_env_float/_env_int` 解析失败 UserWarning。

### T3 — 代码卫生（9 处字符串 `__import__` 清除 + 展示层）
- cli/compilation_service/outcome_settlement_service/observability/l0/demo 全部改正常 import。
- `--on-accent` token 替换 style.css 4 处 `#fff`（AC-4 兑现）。

### T4 — UX 深化（复盘闭环 + 可读性）
- `/v1/review` 台账行带 `decision_question`（决策问题标题）+ `created_at`。
- Web 工作台：待复盘预测列表 + 「成真/落空」结算按钮（闭环第③步）；localStorage 最近 10 条
  会话历史（可回看/清空）；判断耗时显示；首屏示例输出占位；错误态不再静默空白。
- CLI `solve`/`quick-solve` 默认输出 rich 中文面板（5 段合同），`--json` 保留机器可读。

### T5 — 版本 + 测试 + 文档
- `__version__ = "1.9.0"`（`__api_contract_version__` 维持 1.4），pyproject 同步，4 个测试文件版本钉同步。
- 新增 `tests/test_v19_hardening.py`（15 例：EventBus 隔离 / 绑定过滤 / 乐观锁分叉 / env 解析 /
  重试策略 / OpenAI 判别 / mock 检索空集）；扩展 test_v19_review / test_l2 / test_cli。
- `CODE_ARCHITECTURE_REVIEW.md` 续写 §5–§10（调用链/依赖图/问题清单/历史对比/结论）。
- README / `.env.example` 更新。

## 2. 验收标准

| # | 验收 | 方式 |
|---|------|------|
| AC-1 | 全量 pytest 绿（585+ passed / 1 skipped-PG） | `pytest -q` |
| AC-2 | ruff 0 error | `ruff check src tests examples` |
| AC-3 | L0 36/36 + Claim Binding 33/34（CB-034 已知局限） | benchmark |
| AC-4 | API/CLI smoke OK（惰性 app 生效） | import 检查 |
| AC-5 | UI 三文件无 :root 外硬编码色、无 emoji 图标 | 正则扫描 |
| AC-6 | `make release` 包名派生为 v1.9.0 | 脚本检查 |

## 3. 明确不做（P1/P2 后置，记入技术债清单）

- 真实 LLM/Search 凭据接入与垂直场景闭环（产品层，见 `docs/mvp-transition-plan`）。
- `/v1/solve` 流式 SSE；校准曲线 SVG；信念依赖图可视化（突破零构建链前不做）。
- `use_enum_values` 字段类型异构的全局收敛（波及 30+ 模型与全部测试，收益不成比例）。
- PG 行为级 parity 套件扩充（需 CI 环境，本机无 PG 诚实 skip）。
- 6 个骨架 capability 的 LLM 实现（真实 provider 接入后按 benchmark 门槛逐个兑现）。
- 死模型删除（CompanyCase/legacy 契约完整性保留）。

---

## 4. Round 2（同日第二轮，纯代码侧技术债清理）

在第一轮基础上，把定性后置项中**纯代码侧、可安全落地**的部分一次性清掉：

| # | 项 | 落地 |
|---|----|------|
| R2-1 | EventType 声明未发射 | 4 个接真实生命周期点：`ACTION_CREATED`/`EXPERIMENT_STARTED`/`EXPERIMENT_RESOLVED`（`/v1/experiments/{id}/resolve`）、`CONTEXT_INVALIDATED`（compilation persist 后）；`FOUNDER_PROFILE_CHANGED`（无变更路径）与 `COMPANY_CASE_UPDATED`（legacy importer 自有 audit 词汇）记录为预留 |
| R2-2 | L1 生产 harness 未做 schema 校验 | `L1Runner.run(schema_path=...)` 逐行 Draft-07 校验；jsonschema 缺失优雅跳过（dev 依赖）；schema-invalid 与泄漏门一致「拒绝不执行」；现网 7 条案例全过（测试锁定） |
| R2-3 | `claim_binding._scope` 静默回退 | fail-loud（ValueError + 原因） |
| R2-4 | 仓储无 close()/连接生命周期 | SQLite/PG `close()`（幂等）+ `__enter__/__exit__` |
| R2-5 | `make_release` 覆盖率产物泄漏 | `.coverage`/`coverage.xml`/`cobertura.xml`/`.DS_Store` 文件级排除，过滤器抽纯函数 `_should_skip_file` |
| R2-6 | UX 诊断 #3/#4/#7（先进模型数据不渲染） | UI「展开完整模型」渐进披露：信念依赖（中文关系）/ 待确认参数 / 实验 VOI / 个性化 / 模型自检，纯渲染 `solve_summary` 既有投影，零后端改动 |
| R2-7 | 回归测试 | `tests/test_v19_round2.py` 9 例（事件发射 ×2、L1 schema ×2、scope fail-loud、close() ×2、release 过滤器、UI 披露） |

**验收（Round 2）**：pytest 全量 597 passed / 1 skipped、ruff 0 error、L0 36/36、L1 6/6 + 1 泄漏拒绝、CB 33/34、API/CLI smoke OK。

**未动项（有明确理由）**：`harness.comparison_report`（docstring 即标注 Skeleton，冻结案例门已由 `oss_admission_experiment` 负责）；L1 泄漏运行时内容扫描（flag 为作者自审契约，见 MINOR-L1-004）；CB coverage 死指标（数据集扩展前保留）。
