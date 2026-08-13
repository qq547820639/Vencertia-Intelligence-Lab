# Vencertia v1.2.1 迭代实施计划（V-6/V-7 + critic 接线 + PG CI + 文档收尾）

> 主理人：齐活林（Qi）· 日期：2026-08-13
> 上游输入：`docs/agentv11-v112-mapping-review.md` §C（V-6/V-7 落地建议）与 `docs/v1.2-construction-plan.md` §6.4（critic gate 接线预留）
> 范围：本轮一次迭代执行完 **V-6 + V-7 + critic gate solve 接线 + PG CI 服务 + 文档收尾 + git 提交**。

## 0. 裁决

- 跳过 PM（需求已由映射报告 §C 与施工图 §6.4 定义）；流程：架构师（增量施工图）→ 工程师（实现+提交）→ QA（验证）。
- PG：本机无 docker/PG → 不在本机实跑；**在 `.github/workflows/ci.yml` 加 postgres service**，CI 兑现 Release Gate I；本机 `test_postgres_parity.py` 维持 skip+诚实声明。

## 1. 任务范围

| # | 项 | 内容 |
|---|---|---|
| T1 | V-6 BeliefEdge 因果图 | `domain/belief_edge.py`（BeliefEdge 9 类 relation）；`Evidence` 加 `shared_signal_group`；belief 聚合按边关系防 double counting（扩展 belief_engine 折扣） |
| T2 | V-7 ActionState 词表 | `domain/base.py` 扩 `ActionState`（ACT/TEST/HOLD/WAIT/STOP，与既有 DecisionType 共存+映射）；`DecisionOption` 支持 WAIT/STAGE kind；`runtime.py` SolveRequest 加 `mode`（EXPLORE/OPERATE）；`/v1/solve` 增加 Default/Advanced 两层投影（Advanced 含 belief graph/utility/sensitivity/trace，Default 为 5 段合同） |
| T3 | critic gate 接线 | solve 主链路：`ModelCriticGate.should_require(stakes_class, threshold)` 命中时先跑 ChallengerCapability 产出 ModelCritique 再决策；critique 附入 SolveResult |
| T4 | PG CI | ci.yml 加 `services: postgres:16` + `VENCERTIA_PG_DSN` env；`pip install -e ".[postgres]"`；跑 test_postgres_parity.py |
| T5 | 文档收尾 | README 测试数字 483、版本 1.2.1 说明、文档索引补 v1.2 三份文档；DELIVERY_REPORT 加 v1.2/v1.2.1 交付段；docs/ITERATION_LOG 追加 |
| T6 | git 提交 | 全部改动（含上轮 v1.2 未提交的 31 文件）统一提交，message 见下 |

## 2. 硬约束（沿用 v1.2 施工图铁律）

- 向后兼容：483 passed / 1 skipped 零回归；新字段全部可选/有默认值；`ActionState` 与 `DecisionType` 双词表并存（ActionState 是**展示层**映射，DecisionType 是引擎词表，不改引擎语义）。
- 零新运行时第三方依赖；psycopg 仅 `[postgres]` extra（CI 安装）。
- V-7 的 Default 投影 = 现有 SolveResultV11 输出不变（向后兼容）；Advanced 投影为新增可选字段组。

## 3. 执行顺序

架构师施工图 → 工程师实现（T1→T2→T3→T4→T5→T6）→ QA 验证 → 主理人汇总。

## 4. git 提交策略（主理人裁决）

- 提交 1：`feat(v1.2): M0 hardening + V-1~V-5 semantic protocols`（上轮 31 文件）
- 提交 2：`feat(v1.2.1): V-6 BeliefEdge + V-7 ActionState/modes + critic gate + PG CI`
- 提交 3：`docs: v1.2.x delivery reports and walkthrough reviews`
- 不 push（用户未要求），仅本地提交。
