# Vencertia Adaptive Decision System v1.0 — 交付总览

**状态**：✅ 交付完成（QA 两轮验证 PASS）
**交付物**：`Vencertia_Decision_Runtime_v1.0.zip`（3.3MB，324 文件，可独立运行）

## 一句话
AgentV10.2 从 Prompt-driven Multi-Agent Startup Advisory 重构为 **Deterministic Decision Runtime**：LLM 降级为 capability modules（无状态写权），确定性引擎拥有状态变更权，可校准、可迭代、可收敛。

## 核心指标（独立复跑确认）
- **测试**：174 passed, 0 failed（含 QA 独立对抗套件 46 条）
- **L0 Benchmark**：26/26（pass_rate 1.0）；**L1**：6/6（泄漏案例正确拒绝）
- **Demo 闭环**：B2B SaaS MVP → ABSTAIN/DO NOT COMMIT → SELL PAID PILOT → 20 outreach 0 paid → WTP 0.348→0.189 → 重评 → 预测结算 → 校准更新
- **24 项验收**：全部满足（见 docs/implementation-report.md §6）

## 三轮迭代（诚实记录，见 docs/iteration-log.md）
1. 内核可跑：修复 pydantic 递归/枚举混用/模块遮蔽/收敛不可达等 6 问题
2. 接口可交付：CLI 分组重构/L1 参考修正等 4 问题
3. 可靠性强化 + QA 对抗修复：ABSTAIN 必带 next_experiment（MAJOR）、resolved_at aware UTC、status=EVALUATED 持久化

## 关键架构决策（ADR-001~007，docs/architecture-decisions.md）
Agents=capability modules / Deterministic runtime owns state / Decision-Experiment 双空间 / Company Case 证据隔离 / framework-agnostic / benchmark precedes OSS / 允许 ABSTAIN

## 已知限制（不伪装完成）
PG 未实跑（门控安全）/ LLM provider 未真调（默认 mock 离线全功能）/ L0 decision_accuracy=0.615 系 synthetic 口径勿误读 / ECE 分桶产物已文档化

## 下一阶段
1. L2 前瞻预测积累 + 校准重标定启用
2. 真实 Research/LLM 适配器（按 benchmark delta 准入）
3. Postgres 生产化 + 多用户边界 + Portfolio Optimizer 升级
