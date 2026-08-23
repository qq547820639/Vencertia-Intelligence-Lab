# ADR-015 — 与 AIPD-OS 保持独立项目关系（姐妹系统边界）

> 状态：Accepted（v2.0.1）
> 日期：2026-08-23
> 依据：两仓全量代码审查（9 个并行模块审查 + 跨仓实证比对，全部结论附 file:line 证据并做运行复核）

---

## Context

Vencertia 与 AIPD-OS（github.com/qq547820639/AIPD-OS）为同一作者在同一周期内创建的两个系统，共享"诚实性工程"哲学（证据分级、能力不可用即明说、绝不伪造成功、发布证据链）。两者词汇表高度相似（decision / evidence / claim / audit / skill），引发"是否应合并为一个项目"与"是否应整体改造为 SKILL 形态"的架构问题。

## 实证核查结论（审查证据摘要）

1. **零耦合现状**：两仓之间没有任何 import、引用或文档提及（全仓 grep 无命中）。
2. **零代码重复**：376×223 个 Python 文件全对全 shingle 指纹比对，5 行档 ≥4 个共享片段的文件对为 0；同名文件（cli.py / evidence.py / metrics.py 等）difflib 相似度全部 <0.25。
3. **概念同名异物**：两仓的 decision / evidence / maturity / skill 等词汇语义均不同（详见下方词汇表），合并将造成系统性词汇歧义。
4. **硬性合并障碍**：
   - Python 版本窗不相容：AIPD `>=3.9,<3.13`（3.9/3.10 为已验证契约）vs Vencertia `>=3.11`，交集仅 3.11/3.12；
   - 依赖哲学对立：AIPD 以"仅 jsonschema、其余全标准库"为架构原则（LLM 客户端用 urllib 自实现），Vencertia 域层全量建筑在 pydantic/FastAPI/httpx 上；
   - 存储哲学相反：AIPD 为 21+ 张专用表的富关系模型（多租户、版本化迁移、SHA256 冻结 v1），Vencertia 为泛型 `entities` + `event_log` 实体存储（无版本表幂等重放）——共存将产生 decisions/evidence 双真相源；
   - 测试套件物理冲突：同名 `tests/test_cli.py` 在 AIPD 的 `tests/__init__.py` 包结构下合并即触发 pytest import mismatch；Vencertia conftest 顶层依赖 fastapi，AIPD 零依赖环境无法收集。
5. **SKILL 形态核查**：AIPD-OS **已经是**规范 SKILL 形态（根 SKILL.md + `check_skill_package.py` 强制单 SKILL.md + references/scripts/templates 配套），无需改造。Vencertia 的 `src/vencertia/skills/` 是"V11 提示词资产迁移层"（Protocol，无写权），与 SKILL.md 规范形态同名不同物；其确定性引擎核（domain + runtime 引擎 + InMemoryRepository，约 7-8k 行）理论可 skill 化，但需剥离 FastAPI（843 行）/ PG / typer / UI，会移除产品的 Web 决策工作台与 API 面。

## 决策矩阵（weighted-scoring，权重 + 评分 1-5）

| 维度 | 权重 | 合并为一仓 | 整体改造为 SKILL | 维持独立+边界规范化 |
|---|---|---|---|---|
| 职责边界清晰度 | 20% | 2 | 4 | 5 |
| 构建发布流程兼容性 | 15% | 2 | 3 | 4 |
| 依赖关系与部署灵活性 | 15% | 2 | 3 | 5 |
| 长期维护成本 | 15% | 2 | 3 | 4 |
| 功能重叠消除收益 | 10% | 3 | 2 | 3 |
| 向后兼容与迁移风险 | 15% | 2 | 2 | 5 |
| 用户价值与调用便利 | 10% | 3 | 3 | 4 |
| **加权总分** | | **2.20** | **2.95** | **4.40** |

敏感性分析：第 1 名领先第 2 名 1.45 分（>0.3 阈值），所有维度权重 ±10% 波动后排名不变，结论稳健。

## Decision

**维持独立项目，并书面固化姐妹系统边界。** 具体规则：

1. **职责边界**
   - **Vencertia 拥有**：决策质量域——Claim/Evidence/Belief 三层贝叶斯管线、预测登记与结算（PredictionLedger）、校准统计（Brier/ECE）、判断合同、决策台账与复盘。
   - **AIPD-OS 拥有**：产品开发执行域——产品定义管线（Idea→Requirement→Feature）、工程成熟度阶梯（C0–C7）、CAD/BOM/供应链/成本、制造准备与签名发布。
2. **禁止跨仓代码依赖**：两仓不得互相 import、不得共享源码文件、不得读取对方数据库。
3. **互操作仅允许文件级显式契约**：未来如需联动（例如 AIPD 的 claims 导出到 Vencertia 做校准跟踪），必须通过版本化的 JSON 交换格式完成，且须先在本文件追加 ADR 修订。当前**有意不建桥**：AIPD 的 decision 是"Owner 审批工作流条目"，Vencertia 的 PredictionEntry 是"概率预测登记"，语义不同构，强行映射属于伪造集成，违反两仓共同的诚实性原则。
4. **词汇消歧**：跨仓沟通时按下表使用限定词，避免同名异物歧义。

## 词汇消歧表（同名异物）

| 词汇 | 在 Vencertia 中 | 在 AIPD-OS 中 |
|---|---|---|
| decision | 效用优化问题对象 + 预测登记（引擎推进） | Owner 审批队列条目（工作流阻塞构件） |
| evidence | 带权威分级/时效/去重的贝叶斯证据 | 文献登记（kind/title/url/quality） |
| maturity | 无此概念（最接近的是 calibration 统计校准） | C0–C7 工程成熟度阶梯（CAD/制造） |
| skill | V11 提示词资产 Protocol（无写权） | Agent Skill 规范形态（SKILL.md 包） |
| audit/event | 领域事件溯源 event_log | 变更审计 audit_log（before/after） |

## Consequences

- 正向：两仓各自的架构契约（零依赖 / pydantic+FastAPI）、版本线（v5.x / v2.x）、发布体系（签名发布 / 裸 zip）互不干扰；pytest 套件各自独立；词汇表在各自仓内保持自洽。
- 代价：4 组功能等价实现继续平行存在（OpenAI 客户端 urllib vs httpx、指标、mock provider、发布打包），总量约 500 行，接受该代价以换取契约完整。
- 不做的：不合并仓、不抽共享库、不建代码桥、Vencertia 引擎核暂不移出为独立 skill。

## 重新评估触发条件

满足以下任一条件时应重开本决策：
1. 出现第三个同哲学项目，且三者间出现真实的重复维护负担；
2. AIPD-OS 的 claims 导出与 Vencertia 校准跟踪形成真实使用需求（此时按规则 3 建立文件级契约）；
3. 任一仓的部署形态发生根本变化（如 Vencertia 放弃 Web 产品面转为纯库）。
