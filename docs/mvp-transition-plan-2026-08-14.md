# Vencertia 转型 MVP 实施计划（决策复盘器）

> 日期：2026-08-14　基于：`docs/product-strategy-2026-08-14.md`（产品定位裁决：继续做但转型）
> 授权：全权裁决，一次性迭代执行完。

---

## 1. 产品定义（一句话）

**Vencertia 决策复盘器**：不是替你做决定，而是**记录你的判断 → 追踪结果 → 告诉你判断准不准**，用「校准」证明你的决策质量。

## 2. 用户闭环（3 步，最小可用）

```
① 发起决策        复用 /v1/solve，得到可解释判断（5 段合同 + 置信度 + 诚实 ABSTAIN）
     ↓
② 登记预测        关键预测落 PredictionLedger（target + predicted_probability + due_at）
     ↓
③ 记录结果 + 复盘  到期标记成真/落空 → resolve → 仪表盘看命中率 / ECE / 决策台账
```

## 3. 技术映射（关键：引擎资产已具备，零引擎改动）

| 需求 | 现有资产 | 动作 |
|------|----------|------|
| 预测登记 | `PredictionLedger.register` + `/v1/predictions` | 复用 |
| 结果解析 | `resolve_prediction` + `/v1/predictions/{id}/resolve` | 复用 |
| 校准 | `CalibrationEngine.report`（ECE/Brier）+ `/v1/calibration` | 复用 |
| 决策台账 | `DecisionLedger`（`list_decision_records` / `list_decision_outcome_records`） | 复用 |
| 待复盘预测 | `get_open_predictions` | 复用 |
| **聚合视图** | 无 | **新增 `/v1/review`（只读聚合）** |
| **主形态 UI** | 现有「决策工作台」单页 | **重构为「台账 + 校准仪表盘」** |

## 4. 新增 API 契约

`GET /v1/review?project_id={id}` → `{code, data, message}`，`data`：

```
{
  "ledger": [          # 决策台账：推荐 → 行动 → 结果 → 状态
    {"decision_id", "recommendation_zh", "action_taken", "status", "outcome", "updated_at"}
  ],
  "open_predictions": [  # 待复盘预测
    {"id", "target", "predicted_probability", "due_at"}
  ],
  "calibration": {       # 校准概览（复用 CalibrationProfile 投影）
    "n", "sufficient", "verdict", "brier_score", "ece", "hit_rate"
  }
}
```

## 5. 界面结构（重构 index.html/app.js/style.css）

- **顶栏**：品牌 + 「本地离线演示模式」健康指示
- **左列**：发起决策（折叠，复用 solve 表单 + 结果 5 段合同）
- **主区**：决策台账列表（每条：推荐→行动→结果→状态，可「标记结果」）
- **侧栏**：校准仪表盘（待复盘数 / 命中率 / ECE / 布赖尔分）

## 6. P0 范围（本次交付）与明确不做

**做**：聚合端点 + 前端主形态重构 + 测试回归。

**不做（P1/P2 后置）**：真实 LLM/数据接入、多用户权限、校准曲线 SVG 画布（先用数字卡片）、暗色主题、通用「决策工作台」作为主形态。

## 7. 验收标准

| # | 验收 | 方式 |
|---|------|------|
| AC-1 | `GET /v1/review` 返回 ledger + open_predictions + calibration 三块 | pytest |
| AC-2 | 现有 570 测试全过（引擎/数据模型零改动证明） | pytest |
| AC-3 | 前端主界面为台账+仪表盘，不再以「给你判断」为唯一主角 | 代码审查 + 预览 |
| AC-4 | 无 emoji 图标 / 无紫粉渐变 / :root 外零硬编码色 | 正则扫描 |
| AC-5 | ruff 0 error | lint |

## 8. 变更记录

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-08-14 | 初版 | 产品定位裁决后落地转型 MVP |
