---
name: vencertia
description: 商业决策与决策质量技能。当用户需要判断"要不要做/值不值得投/假设是否成立"、需要把想法整理成可验证的决策、需要记录判断并追踪命中与校准（Brier/ECE）、复盘决策质量、或基于已验证证据生成商业计划时使用。产品实现类意图（做产品/图纸/BOM/供应链）不要走本技能，应走 aipd-orchestrator；不确定时由 product-decision-router 技能裁决。
---

# Vencertia — 决策参谋 + 账房先生

本仓是决策复盘与校准系统（v2.0.1）。本 SKILL.md 是 Agent 调用入口；产品形态（FastAPI Web 决策工作台）保持独立可用，二者共用同一套 CLI 与内核。

## 核心原则（不可违反）

1. **你不替用户做决定**——用户是决策者，你产出判断合同（当前判断/为什么/最大未知/下一步/什么会改变判断）。
2. **证据不足就明说 ABSTAIN**，并给出可先做的最小实验；绝不编造漂亮答案。
3. **一切状态变更走 CLI**：不得让模型输出直接写库。校准、台账、信念更新由确定性引擎负责。
4. 上游路由（product-decision-router）转来的 NO_GO/ABSTAIN 结论**原样呈现**，不得为进入产品执行段而美化。

## 安装与运行

```bash
pip install -e .          # 需要 Python >= 3.11
vencertia --help
```

LLM 能力需配置 `MODEL_PROVIDER=openai_compatible` + 端点凭据；未配置时相关命令**响亮失败而非静默降级**（产品裁决 v2.0.1：演示模板已从产品路径移除）。

## 常用命令（CLI 为唯一事实源，以 `vencertia --help` 为准）

| 任务 | 命令 |
|---|---|
| 从一句话想法开始 | `vencertia idea "想法文本" [--json]` |
| 完整求解（编译→研究→评估→台账） | `vencertia solve ...` / `vencertia quick-solve ...` |
| 决策编译/评估/敏感度/追踪 | `vencertia decision-compile / decision-evaluate / decision-sensitivity / decision-trace` |
| 证据录入与绑定 | `vencertia evidence-add / evidence-bind / evidence-import` |
| 研究规划与执行 | `vencertia research-plan / research-run` |
| 最小实验建议 | `vencertia experiment-propose <decision_id>` |
| 结果登记（触发信念更新与预测结算） | `vencertia outcome-record <action_id> <result>` |
| 预测登记与结算 | `vencertia prediction-create / prediction-resolve` |
| 校准仪表盘 | `vencertia calibration-report [--scope ALL]` |
| 由证据生成商业计划 | `vencertia bp ...`（数字必须挂到假设清单，缺数据处如实标注） |
| 回归基准 | `vencertia benchmark-run --level L0|L1|L2` |

## 与 AIPD-OS 的交接

当决策结论为 GO 且用户意图转向产品实现：按 `product-decision-router` 仓 `schemas/handoff_v1.json` 契约产出交接 JSON（v1 阶段由模型转述生成；`export-decision` 命令为路线图待实现项）。NO_GO/ABSTAIN 不进入交接。

## 已知边界（诚实声明）

- 手工录入证据的信念回放、校准映射低端钳制等为审查在案问题，结论解读时留意 `docs/adr/` 与审查报告。
- AI 适配器已实现但未经真实凭据端到端验证（README 已声明）。
