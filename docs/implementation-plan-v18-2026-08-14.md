# Vencertia v1.8 实施计划（Web 决策工作台 MVP）

> 日期：2026-08-14
> 输入：10,000 用户评语 Top 痛点（复杂度 10.5% / 维护成本 10.4% / LLM 对比 7.2%——"只想做个决定，不想先学 belief/utility"）

## 0. 背景与裁决

CLI/API 的 projection 层（5 段合同 / 概率文案 / 透明度 / Model Critic）已完全就绪，但评语反映的最大痛点始终在**交互层**：用户不想要命令行和方法论术语。本轮做一个**零构建链的 Web 决策工作台**（FastAPI 静态托管 + 原生 HTML/CSS/JS，不引入 Node 构建链），直接复用已就绪的 presentation 层。

版本 **1.8.0**（新增 UI 面，`__api_contract_version__` 维持 1.4——API 契约零变化，仅新增静态资源托管）。

## 1. 任务清单

### T1 — 前端静态资源 `src/vencertia/ui/`
- `index.html`：决策工作台单页——solve 表单（problem_text 必填 + mode 选择 EXPLORE/OPERATE + 可选 options JSON）+ 结果区（5 段合同卡片 + advanced 折叠面板）。
- `app.js`：fetch `POST /v1/solve`（默认 `view=summary`；advanced 切换 `advanced=true`）；渲染中文字段（current_judgment_zh / confidence_phrase / rationale / biggest_unknown / next_step / change_condition / model_critique / experiment_voi / personalization）；错误 envelope 处理。
- `style.css`：卡片式、浅色主题、渐进披露（默认 5 段，advanced 折叠）。

### T2 — 后端托管
- `api.py` `create_app`：`app.mount("/static", StaticFiles(directory=ui_dir))` + `@app.get("/", include_in_schema=False)` 返回 `index.html`。
- 零新第三方依赖（`fastapi.staticfiles.StaticFiles` 随 fastapi 内置）。

### T3 — 测试 + 版本 + 文档 + push
1. `tests/test_v18_ui.py`：`GET /` 返回 200 + HTML；`GET /static/app.js` 200；UI 经 `api_client` 走一遍 `POST /v1/solve` 返回 summary 结构（端到端）。
2. 版本 1.8.0（`__init__.py` / `pyproject.toml` + 4 个测试文件断言同步 1.7.0→1.8.0）。
3. README 加"Web UI"一节（`make api` 后访问 http://localhost:8000/）。

## 2. 验收

1. `pytest tests/ -q` 565+新测试全绿；`ruff check src tests` 0 error。
2. `GET /` 200 且含决策工作台表单；`GET /static/app.js` 200。
3. 前端表单发起 solve → summary 中文字段完整渲染（端到端测试锁定关键字段存在）。
4. git 提交 + push origin main。
