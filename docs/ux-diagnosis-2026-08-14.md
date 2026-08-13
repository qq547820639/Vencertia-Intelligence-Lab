# Vencertia 决策工作台 UX 诊断报告

> 日期：2026-08-14　对象：Web 决策工作台（`src/vencertia/ui/`）+ CLI + API
> 诉求：用户体验很差，帮我看看为什么。本报告只做诊断与建议，不改动任何代码。

---

## 1. 总体结论（一句话）

**不是算法不行，是「能力已有、用户感知不到」——展示层把用户挡在了门外。** 系统里算好的效用、敏感度、信念关系、参数来源全都存在，但界面用原始 JSON 和文字列表呈现，普通用户看不懂；同时每次决策引擎被白白跑两遍，慢且无反馈。这与 v1.3 那轮 10000 条评语提炼出的头号痛点（复杂度 10.5%／「只想做个决定」）是同源问题，只是换了个 Web 壳子再次出现。

---

## 2. 诊断根因（按四大症状）

### 症状一：太慢 / 没反馈

| # | 根因 | 证据 |
|---|------|------|
| 1 | **一次「开始判断」发两次完整 solve 请求**：`?view=summary` 一次、`?advanced=true` 一次，确定性引擎各跑一遍；第二次失败还会和已渲染好的 summary 形成「有结果 + 报错」的矛盾态 | `app.js:155-173` |
| 2 | 全程只有按钮文案「判断中…」，无阶段提示、无耗时、无超时、无取消；`/v1/solve` 无流式 | `app.js:141,155-178` |

> 关键事实：`runtime.solve()` 每次请求本就会计算 `advanced_view`（API 层仅在 `advanced=false` 时把它置 None），所以前端拿全数据其实只需**一次** `?view=summary&advanced=true`，两次请求是纯浪费。

### 症状二：结果看不懂

| # | 根因 | 证据 |
|---|------|------|
| 3 | 效用 `{option_id: float}` 与敏感度 `DecisionSensitivity` 直接 `JSON.stringify` 倒进 `<pre>`，业务用户面对的是机器格式 | `app.js:127-134` |
| 4 | 信念依赖图是纯文字列表「A → B（关系）」，没有用上 `solve_summary` 已产出的 `belief_dependencies`／`provenance_summary`（带中文关系标签） | `app.js:109-117`；`presentation/__init__.py:366-386` |
| 5 | 风险容忍度下拉直接暴露 0.3／0.5／0.8 数字，业务用户无感 | `index.html:39-41` |
| 6 | 健康指示器显示「v? · provider mock」，对非技术用户是噪音 | `app.js:26-27` |
| 7 | 敏感度里的「稳健性」若直接展示会是 `ROBUST_DECISION`／`FRAGILE_DECISION` 英文枚举，未映射成中文 | `domain/decision_trace.py:55` |

### 症状三：操作别扭

| # | 根因 | 证据 |
|---|------|------|
| 8 | options 要求手写 JSON，解析失败提示「options 不是合法 JSON：…」是开发者语言，且错误显示在右侧结果区而非出错字段旁 | `app.js:146-150`；`index.html:45-47` |
| 9 | 每次求解新建 `project_id "ui-"+Date.now()`，无会话历史；点「再问一个」上一个结果永久消失 | `app.js:142,191-194` |
| 10 | 桌面端结果本就在右栏可见，却整页 `scrollIntoView` 把表单推出视口 | `app.js:171` |

### 症状四：页面简陋

| # | 根因 | 证据 |
|---|------|------|
| 11 | 语义浅色色值／代码块深色全硬编码；`--warn`／`--ok` 定义后零引用，Token 体系半途而废 | `style.css:65,70,81,82,88` |
| 12 | 首屏右侧结果栏 `hidden` 纯空白，用户输入前不知道输出长什么样 | `index.html:53` |
| 13 | 焦点态仅 textarea/select 有、button 无 `:focus-visible`；字阶扁平（h1 18px）；`pre` 缺等宽字体 | `style.css:50,34,43,87-89` |
| 14 | 间距/圆角非 4px 网格；触摸目标 < 44px | `style.css:26,52,77` |

### 附加：CLI / API 侧

| # | 根因 | 证据 |
|---|------|------|
| 15 | CLI `solve` 默认输出也是 `print_json` 原始 JSON，未复用 5 段合同的可读性 | `cli.py:59-64` |

---

## 3. 修复建议（按优先级，未执行）

### P0（先做，性价比最高）

1. **合并为单请求**：`/v1/solve` 增加 `view=summary&advanced=true` 合并模式，单次引擎运行同时返回 `{summary, advanced_view}`；前端一次请求拿全（顺带消除症状一的矛盾态）。
2. **原始 JSON → 结构化渲染**：效用渲染为「方案→调整后效用」、敏感度渲染为「当前建议／稳健性／翻转阈值」、信念图带中文关系标签、浮点噪声四舍五入。
3. **设计令牌补全**：补 `--danger-soft/--danger-border/--warn-soft/--warn-border/--accent-border/--code-bg/--code-fg`，全量替换硬编码色值。

### P1（高价值）

4. 首屏空态：结果区预置「示例输出」占位。
5. 风险下拉自然语言（「风险厌恶／中性／偏好」）。
6. 字段级错误：JSON 错误显示在 options 输入框下方。
7. 会话历史（localStorage 最近 10 条，可回看/清空）。
8. 进度反馈：耗时计时 + 加载态。
9. 仅 <860px 单列时才滚动。
10. `:focus-visible` 焦点环 + 8 级字阶 + 等宽字体。
11. 健康指示器友好化（mock →「本地离线演示模式」）。
12. CLI `solve` 默认输出 rich 面板（非 raw JSON）。

### P2（顺手）

13. 结果淡入过渡（含 `prefers-reduced-motion` 降级）。
14. 间距 4px 网格 token 化。
15. 按钮触摸目标 44px。

### 建议后置（收益不成比例，暂不动）

- 暗色主题；信念图 SVG 画布（需引入布局库，超出零构建链约束）；`/v1/solve` 流式 SSE（真实 LLM 接入、延迟成硬伤时再上）。

---

## 4. 涉及文件

- `src/vencertia/ui/index.html`（69 行）
- `src/vencertia/ui/app.js`（197 行）
- `src/vencertia/ui/style.css`（92 行）
- `src/vencertia/api.py`（`/v1/solve`，`525-540` 行）
- `src/vencertia/cli.py`（`solve`，`52-64` 行）
- `src/vencertia/presentation/__init__.py`（`solve_summary`，`274-394` 行）

---

## 5. 结论

体验差的根因是**确定性、且已集中体现在展示层**的 15 项问题，修复全部落在前端三文件 + API 一个端点 + CLI 一个命令，不涉及引擎算法或数据链路。是否动手、何时动手，由你拍板。
