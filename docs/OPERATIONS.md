# Operations（v1.1.1）

> 面向部署/运维的实操手册（GAP-06）。开发细节见 `docs/ARCHITECTURE.md`、
> `docs/OVERVIEW.md`；Provider 详见 `docs/PROVIDERS.md`。

## 1. Installation

```bash
# Python >= 3.11（开发/CI 用 3.13.12）
git clone git@github.com:qq547820639/Vencertia-Intelligence-Lab.git
cd "Vencertia Intelligence Lab"
make install            # pip install -e ".[dev]"
export PYTHONPATH=src   # 运行前必须
```

依赖：`pydantic>=2.10`、`fastapi>=0.115`、`uvicorn>=0.30`、`typer>=0.12`、
`rich>=13`、`httpx>=0.27`（PostgreSQL 另需 `psycopg[binary]>=3.1`）。

## 2. Environment variables（全表）

所有设置均通过 `VENCERTIA_*` 环境变量覆盖，默认完全离线可用
（`src/vencertia/config.py` 是唯一事实来源）。

| 变量 | 默认 | 说明 |
|---|---|---|
| `VENCERTIA_DB_DSN` | `sqlite:///data/vencertia.db` | SQLite DSN |
| `VENCERTIA_PG_DSN` | 空 | PostgreSQL DSN（启用 PG 路径） |
| `VENCERTIA_MODEL_PROVIDER` | `mock` | `mock` / `openai_compatible` |
| `VENCERTIA_OPENAI_BASE_URL` | 空 | OpenAI-compatible base URL |
| `VENCERTIA_OPENAI_API_KEY` | 空 | API key |
| `VENCERTIA_OPENAI_MODEL` | `gpt-4o-mini` | 模型名 |
| `VENCERTIA_SEARCH_PROVIDER` | `mock` | `mock` / `http`（GAP-02） |
| `VENCERTIA_SEARCH_URL` | 空 | HTTP 搜索端点（`http` 必填，否则 fail loud） |
| `VENCERTIA_SEARCH_API_KEY` | 空 | HTTP 搜索鉴权 |
| `VENCERTIA_SEARCH_TIMEOUT` | `15.0` | HTTP 搜索超时（秒） |
| `VENCERTIA_POLICY_VERSION` | `1.0` | EvidencePolicy 版本标识 |
| `VENCERTIA_LOG_LEVEL` | `INFO` | 日志级别 |
| `VENCERTIA_RISK_AVERSION` | `0.25` | 决策风险厌恶 |
| `VENCERTIA_MINIMUM_MARGIN` | `0.08` | 最小决策 margin |
| `VENCERTIA_MAX_CRITICAL_UNCERTAINTY` | `0.45` | 关键不确定度上限 |
| `VENCERTIA_BINDING_CONFIDENCE_THRESHOLD` | `0.6` | 绑定置信度阈值 |
| `VENCERTIA_BINDING_MIN_SCORE` | `0.7` | 绑定最低匹配分（GAP-01） |
| `VENCERTIA_BINDING_AMBIGUITY_MARGIN` | `0.1` | top1/top2 歧义余量（GAP-01） |
| `VENCERTIA_BINDING_REJECT_THRESHOLD` | `0.4` | 弱候选噪声下限（GAP-01） |
| `VENCERTIA_SENSITIVITY_STEP` | `0.01` | 灵敏度扫描步长 |
| `VENCERTIA_FRAGILE_FLIP_THRESHOLD` | `0.10` | 脆弱翻转距离（GAP-03） |
| `VENCERTIA_FRAGILE_MARGIN` | `0.05` | 脆弱 margin（GAP-03） |
| `VENCERTIA_MODERATE_FLIP_THRESHOLD` | `0.25` | 中等翻转距离（GAP-03） |
| `VENCERTIA_MODERATE_MARGIN` | `0.12` | 中等 margin（GAP-03） |
| `VENCERTIA_RESEARCH_MAX_QUESTIONS` | `3` | 研究问题数上限 |
| `VENCERTIA_RESEARCH_MAX_ROUNDS` | `3` | 研究轮次上限 |
| `VENCERTIA_RESEARCH_QUERIES_PER_ROUND` | `3` | 每轮查询数 |
| `VENCERTIA_RESEARCH_STOP_MARGINAL_VALUE` | `0.02` | 停止：边际价值阈值 |
| `VENCERTIA_RESEARCH_STOP_DUPLICATE_RATE` | `0.5` | 停止：重复率阈值 |
| `VENCERTIA_DEDUP_SIMILARITY_THRESHOLD` | `0.8` | 去重相似度阈值 |
| `VENCERTIA_FRESHNESS_HALF_LIFE_DAYS` | `90.0` | 新鲜度半衰期 |
| `VENCERTIA_PROVIDER_MAX_RETRIES` | `2` | Provider 重试次数 |
| `VENCERTIA_PROVIDER_TIMEOUT_SECONDS` | `30.0` | Provider 超时 |
| `VENCERTIA_PROVIDER_RETRY_BACKOFF_BASE` | `0.5` | 重试退避基数 |
| `VENCERTIA_CALL_LOG_ENABLED` | `true` | 是否记录 ProviderCallRecord |

## 3. SQLite（默认）

- 默认 DSN：`sqlite:///data/vencertia.db`（仓库内 `data/` 目录）。
- 生产建议把 `VENCERTIA_DB_DSN` 指向仓库外路径，避免打包/备份时误带。
- 迁移脚本：`src/vencertia/repositories/migrations/0001_initial.sql`（SQLite）。

## 4. PostgreSQL

- 设置 `VENCERTIA_PG_DSN`（如 `postgresql://user:pass@host:5432/vencertia`）。
- 迁移脚本：`src/vencertia/repositories/migrations/0002_pg.sql`。
- PG 相关测试在未配置 DSN 时自动 skip（pytest 中 1 skipped 即 PG 门控）。

## 5. Mock Provider（默认）

- `VENCERTIA_MODEL_PROVIDER=mock`：全离线、确定性，无外部 API。
- `VENCERTIA_SEARCH_PROVIDER=mock`：内置 3 条文档，支持研究/绑定闭环。

## 6. OpenAI-compatible Provider

```bash
export VENCERTIA_MODEL_PROVIDER=openai_compatible
export VENCERTIA_OPENAI_BASE_URL=https://api.example.com/v1
export VENCERTIA_OPENAI_API_KEY=sk-...
export VENCERTIA_OPENAI_MODEL=gpt-4o-mini
```

未配 key 时只 wire 不调用；调用失败按 ADR-012 结构化重试/报错。

## 7. HTTP Search Provider（GAP-02）

```bash
export VENCERTIA_SEARCH_PROVIDER=http
export VENCERTIA_SEARCH_URL=https://your-search-endpoint/v1/query
export VENCERTIA_SEARCH_API_KEY=...      # 可选
export VENCERTIA_SEARCH_TIMEOUT=15
```

- **Generic HTTP Search adapter implemented. No commercial search vendor is
  bundled. Live use requires user-supplied endpoint and credentials.**
- `http` 但 URL 为空 → 启动 fail loud（`ProviderUnavailableError`），
  **禁止静默退回 Mock**。
- 响应契约：顶层 JSON 数组，或含 `results`/`items`/`data` 数组的对象；
  每条含 `title`（必需）以及可选 `url`/`link`、`snippet`、`content`、
  `published_at`、`source`；额外字段保留在 `metadata`，不泄漏进 Domain。

## 8. API startup

```bash
make api                       # uvicorn vencertia.api:app --port 8000
# 或
PYTHONPATH=src python -m uvicorn vencertia.api:app --host 0.0.0.0 --port 8000
```

健康检查：`GET /health`（返回 provider 选择、版本等）。

## 9. CLI usage

```bash
PYTHONPATH=src python -m vencertia.cli --help
PYTHONPATH=src python -m vencertia.cli demo                     # 内置 B2B SaaS 闭环 demo
PYTHONPATH=src python -m vencertia.cli solve <request.json>     # 从 JSON 跑完整 solve
PYTHONPATH=src python -m vencertia.cli benchmark run --level L0
PYTHONPATH=src python -m vencertia.cli benchmark run --level CLAIM_BINDING
PYTHONPATH=src python -m vencertia.cli benchmark run --level L1
PYTHONPATH=src python -m vencertia.cli migrate-v10.2 <dir>      # legacy V10.2 导入
```

## 10. Tests

```bash
make test                      # 全量 pytest
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m pytest tests/qa_v11 -q    # v1.1 QA 对抗套件
```

## 11. Benchmarks

```bash
make benchmark            # L0（36/36）+ legacy 参考
make benchmark-binding    # Synthetic Claim Binding Benchmark（GAP-04，独立）
make benchmark-all        # L0 + Binding
```

- `benchmark-binding` 输出明确标注 **Synthetic Claim Binding Benchmark
  （NOT real-world accuracy）**；8 项指标 + Coverage；已知局限单独标记
  `KNOWN-LIMIT`，不隐藏。

## 12. CI

```bash
make ci                    # lint（ruff）+ test + benchmark + api-smoke + cli-smoke
make verify                # test + benchmark + API/CLI import smoke
```

等价 CI 门禁：`ruff check src tests examples` → 全量 pytest → L0 基准 →
API/CLI import 冒烟。

## 13. Database location

- SQLite：默认 `data/vencertia.db`（`VENCERTIA_DB_DSN` 可改）。
- 备份：停止写入后复制文件即可；PG 用标准 `pg_dump`。

## 14. Logging

- `VENCERTIA_LOG_LEVEL=INFO`（DEBUG 可开细粒度）。
- 事件日志：`event_log` 表（Event Log，非 Event Sourcing），用于审计/回放。
- Provider 调用：`ProviderCallRecord`（kind/provider/model/latency/tokens/
  cost/success/error_type）；**红线：不记录 prompt / 敏感内容**。

## 15. Provider failure handling

- 失败分类：Timeout / RateLimit / InvalidJSON / SchemaMismatch / Unavailable /
  Empty / Partial（ADR-012）。
- 搜索失败运行期：记录 `PROVIDER_FAILED` 事件 + graceful degradation
  （研究停止规则诚实声明 `SEARCH_EXHAUSTED`），**不产生伪 Evidence、
  不修改 canonical 状态、不 silent fallback mock**（GAP-02）。

## 16. Migration

- 目录：`src/vencertia/repositories/migrations/`
  - `0001_initial.sql`（SQLite 初始 schema）
  - `0002_pg.sql`（PostgreSQL）
  - `0003_v1_1.sql`（v1.1 扩展表）
- 升级顺序：备份 → 应用增量 SQL → 跑 `make test` 验证。
- v1.0 → v1.1 兼容：`BindingStatus.UNBOUND` 兼容别名保证旧持久化数据可读
  （GAP-01）。

## 17. Release commands

```bash
make release   # scripts/make_release.py → Vencertia_Intelligence_Lab_v1.1.1.zip
```

- 排除：`.git` / 缓存 / `*.db` / `*.sqlite*` / `*.zip` / `dist` / `build` /
  `*.egg-info` / `.env` / coverage。
- 发布前必须：`make ci` 全绿 + `make benchmark-all` + 文档数字与代码一致
  （GAP-09）。

## 18. Troubleshooting

| 症状 | 原因 | 处理 |
|---|---|---|
| `search_provider=http requires VENCERTIA_SEARCH_URL` | 配了 http 未配 URL | 设置 `VENCERTIA_SEARCH_URL` 或改回 `mock` |
| 1 test skipped | PG 门控未配 DSN | 不需要 PG 则忽略；需要则设 `VENCERTIA_PG_DSN` |
| `ModuleNotFoundError: vencertia` | 未设 PYTHONPATH | `export PYTHONPATH=src` |
| `Unknown model_provider` | 拼写错误 | 检查 `VENCERTIA_MODEL_PROVIDER` |
| Provider 超时/限流 | 网络/配额 | 检查 `VENCERTIA_PROVIDER_*` 重试与超时设置 |
| L0 数字不对 | 文档引用旧状态 | 以 `docs/BASELINE_V1_0.md` 三状态表核对（GAP-07） |
| 事件缺失 | EventBus 未接 sink | API/CLI 用 `build_container()` 自动接线 |
