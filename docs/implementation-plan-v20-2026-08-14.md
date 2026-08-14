# Vencertia v2.0 实施计划（想法 → 决策 → 商业计划 全路径，混合形态）

> 日期：2026-08-14
> 基线：v1.9.1（复盘闭环完整，611 passed / 9 skipped）
> 裁决：产品定位不冲突但只覆盖中段。按「规则脊椎 + skill 肌肉」混合形态一次性打通全路径：
> 入口层（想法→结构化决策）+ 内核层（不变）+ 出口层（决策→BP）+ Skill 层（V11 经验资产迁移 + 编排校验）。

## 0. 定位声明（与产品战略一致）

- Vencertia 不是 BP 生成器，而是**决策质量系统**；BP 是决策系统的下游产物。
- 「漂亮 BP」的叙事由 skill（经验资产）生成，**数字与断言必须引用假设登记表**（引用校验门），
  数据不足章节诚实 N/A —— BP 里最难造假的部分由确定性引擎提供。
- 经验以「版本化提示词 + 结构化输出契约」为一等资产（谱系指向 legacy V11 源提示词），
  不再散落为硬编码 Python 字符串。

## 1. 任务清单（一次性执行）

| # | 任务 | 落地 |
|---|------|------|
| T1 | 入口层 | `runtime/idea_intake.py` IdeaIntakeService：复用 DecisionCompiler + UncertaintyEngine，产出决策问题/假设清单（LLM_PROPOSED 显式标注）/最大未知/就绪 SolveRequest，零持久化；`POST /v1/ideas/assess`；CLI `vencertia idea`；UI「从想法开始」面板 + 一键转入决策判断 |
| T2 | 出口层 | `runtime/bp_composer.py` BusinessPlanComposer：从持久化状态（Decision/Trace/Sensitivity/Beliefs/Evidence/Experiments/Record/Calibration）组装 7 章 BP 骨架，市场无证据即诚实 N/A；`POST /v1/bp` 返回 view + markdown + narratives + traces；CLI `vencertia bp [--out]`；UI 台账「生成 BP」+「复制全文」 |
| T3 | Skill 层 | `vencertia/skills/`：SkillMetadata（版本/谱系/契约/阶段）+ SkillCandidate（候选无写权）+ SkillRegistry + SkillRouter（阶段路由 + 双重校验门：pydantic 契约 + 引用校验「数字必须有 source_claim_id」）；`biz.py` 迁移 5 个 V11 专家（market/financial/plan/founder/execution，提示词模板 + mock 确定性回退，真实 LLM 即插即用）；`GET /v1/skills` 资产目录；CLI `vencertia skills` |
| T4 | 容器 | `ApplicationContainer.skills / skill_router`（组合根装配，与 providers 同源） |
| T5 | 测试 | `tests/test_v20_fullpath.py` 10 例（入口结构/全路径/BP 七章+叙事+校验/404/市场证据后 N/A 解除/skill 目录/坏引用 REJECTED/坏契约 REJECTED/UI 接线） |
| T6 | 版本/文档/发布 | `__version__=2.0.0`（api_contract 维持 1.4，纯增量端点）；README + 本计划 + CODE_ARCHITECTURE_REVIEW 四层注记；commit + push |

## 2. 验收

- pytest 全量 621+ passed（PG parity skip 数不变）；ruff 0 error；L0/L1/CB 不回退。
- 端到端：idea assess → 转入 solve → 台账标记行动/复盘 → 生成 BP（七章 + 3 skill 叙事 OK + 引用校验门生效）。
- 坏 skill（引用不存在的 claim）被 REJECTED 且不出现在产物中（测试锁定）。
- mock 模式下全链路离线可跑（deterministic 模板 + 诚实声明）；配置真实 LLM 后 skill 走 generate_structured。

## 3. 明确不做（诚实边界）

- 真实 LLM 凭据验证与叙事质量评估（管道已建，泉水需用户接入）。
- 市场/财务数字的真实性（引用校验保证"有出处"，出处本身的质量由证据链与校准负责）。
- 幻灯片/排版（"漂亮"的视觉层），BP 输出为 Markdown 结构，可导入任意排版工具。
- FounderDiagnosis skill 在无创始人数据时诚实 N/A（不编造画像）。
