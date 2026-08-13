# Vencertia v1.6 实施计划（架构收尾：依赖反转 + QA 观察项清零）

> 日期：2026-08-14
> 输入：`docs/v1.5-refactor-plan.md`（架构师留档：runtime.py solve() 内联投影反转依赖留待 v1.6）+ v1.5 QA 报告观察项

## 0. 背景与裁决

v1.5 重构把展示层迁到 `vencertia.presentation` 独立包，但**刻意留了一处未完成**：`runtime.py` 的 `solve()` 仍在引擎层内联组装中文投影（`BELIEF_RELATION_ZH`/`PROVENANCE_ZH` 直接 import + for 循环生成 `relation_zh`/`provenance_zh`）。本轮完成这处依赖反转，并清零 QA 的三条观察项。

版本：**1.6.0**（patch 级收尾也可，但 presentation 新增公开函数属 minor 增量；`__api_contract_version__` 维持 1.4 不动——DTO 字段零变化）。

## 1. 任务清单（3 项，全部零行为变更）

### T1 — presentation 包补 `__all__`（QA 观察项 1）
`src/vencertia/presentation/__init__.py` 末尾补 `__all__`，与 runtime shim 的 18 名对齐（11 常量 + 7 函数）。新增函数后补为 19 名。

### T2 — runtime/__init__.py 改新路径（QA 观察项 2）
第 42-46 行 `from vencertia.runtime.presentation import (estimate_phrase, localize_error_message, probability_level)` 改为 `from vencertia.presentation import ...`，消除经 deprecated shim 的间接依赖。

### T3 — runtime.py solve() 反转依赖（架构师留待 v1.6，核心）
1. `presentation/__init__.py` 新增纯函数 `project_advanced_view(belief_graph_rows: list[dict], options) -> tuple[list[dict], list[dict]]`，封装 `relation_zh`/`provenance_zh` 组装逻辑（中文映射常量单一归宿 presentation 层）。
2. `runtime.py` 第 912-935 行改为调用该函数，删除对 `BELIEF_RELATION_ZH`/`PROVENANCE_ZH` 的直接 import。
3. `runtime/presentation.py` shim 与 `presentation.__all__` 同步补 `project_advanced_view`。

## 2. 零回归保障

- DTO 字段不变：`advanced_view.belief_graph[].relation_zh`、`advanced_view.parameter_provenance[].provenance_zh` 保持输出（`test_v13_transparency.py`、`test_v12_v7_action_state.py` 锁定）。
- 纯函数行为等价：`project_advanced_view` 与内联逻辑逐字节一致。
- 基线：559 passed / 1 skipped / 0 failed；重构后必须不变。

## 3. 验收

1. `pytest tests/ -q` 559/1/0；`ruff check src tests` 0 error。
2. Grep 确认 `runtime.py` 不再 import `BELIEF_RELATION_ZH`/`PROVENANCE_ZH`。
3. `python -c "from vencertia.presentation import *"` 只暴露 19 名（无 typing 杂项）。
4. git 提交 + push origin main。
