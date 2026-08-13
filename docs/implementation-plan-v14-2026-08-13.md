# Vencertia v1.4 迭代实施计划（P1 批次 + canonical 收尾 + push）

> 主理人：齐活林（Qi）· 日期：2026-08-13
> 上游输入：`docs/prd-v13-ux-2026-08-13.md`（P1×5/P2×5 需求池，含验收标准）
> 范围：本轮一次迭代执行完 **P1×5 + 文档文件重命名规范化 + git push**。

## 0. 裁决

- 跳过 PM：P1/P2 需求池已在 v1.3 PRD 中定义（含验收标准），直接架构师出施工图。
- 版本：**1.4.0**（minor，P1 批次为新功能；`__api_contract_version__` 保持 1.3 不动——本轮无 API 契约变更？P1-2 证据批量导入会新增 API 端点——裁决：contract 升 1.4）。
- git：全部完成后 push origin main（本地领先 8 提交 + 本轮新提交一并推送）。

## 1. 任务范围

| # | 项 | 内容（PRD 验收标准为依据） |
|---|---|---|
| P1-1 | 实验 VOI 可见化 | solve_summary 实验段投影 decision_change_rule 近似文案 + 停止条件（"实验做完如何决定够了"）；experiment 输出带可读的"什么结果会改变决策" |
| P1-2 | 证据批量导入入口 | CLI `evidence import` 命令（JSON/JSONL 文件 → EvidencePolicy 校验 → 候选入库，去重/冲突报告）；API `POST /v1/evidence/import` 端点 |
| P1-3 | 个性化可见化 | summary 投影用户 StakesProfile/Objective/约束（"风险偏好/最大可承受损失"中文段），无 profile 时省略 |
| P1-4 | 快速求解 | CLI `quick-solve`（或 solve --quick）一条命令：建项目→决策→solve→summary 全链路，demo 级体验 |
| P1-5 | 校准复盘文案 | calibration 命令输出中文解读（Brier/ECE 含义 + 样本不足提示 + 分桶明细） |
| P2-1 | 文档文件重命名规范化 | docs/ 大写文件名全部重命名为小写连字符（ARCHITECTURE.md→architecture.md 等），同步所有 .md 交叉引用 + README 索引 + 代码内文档引用（如有） |

## 2. 硬约束

- 向后兼容铁律：533 passed / 1 skipped 零回归；新端点/命令不破坏既有契约。
- 零新第三方依赖；中文文案集中 `runtime/presentation.py`（复用 v1.3 基础设施）。
- P1-2 导入走既有 `EvidencePolicy`/dedup 管线（Candidate→Validation→持久化铁律），不得绕过。

## 3. 执行顺序

架构师施工图 → 工程师实现（P1-1→P1-5→P2-1）→ QA 验证 → 主理人 push origin main + 汇总。

## 4. 风险

- P2-1 文档重命名是全局引用变更（docs/ 46 个 md 互相引用 + README + 可能的代码 docstring 路径引用）——施工图必须列全引用面，工程师用脚本化方式（find+sed 或逐个核对）执行，QA 用链接检查脚本验证 0 断链。
- P1-2 导入端点需防重复导入（幂等：同 fingerprint 跳过并报告）。
- push 前最终 `git log` + `pytest` + `ruff` 三绿确认。
