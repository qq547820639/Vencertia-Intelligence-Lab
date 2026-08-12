# ITERATION — v1.1 RC Hardening Round 3（QA 干净环境全量回归 + 10 Gate 核验）

> HISTORICAL SNAPSHOT — 记录 v1.1.1 交付时点事实，不作为 v1.1.2 的 authority。

> 执行人：严过关（QA）· 日期：2026-08-12 · 版本：1.1.1（工作区）
> 基线：docs/ITERATION_V1_1_RC_2.md（对抗 edge-case）· 本轮：干净 venv 全量回归 + Release Gate 独立核验。

## 1. 干净环境

```text
venv        = /tmp/v111rc-venv（由 /Users/panhao/.workbuddy/binaries/python/envs/default/bin/python -m venv 创建）
install     = pip install -e ".[dev]"（成功，vencertia-decision-runtime 1.1.1）
python      = 3.13.12（venv 内）
PYTHONPATH  = src（Makefile 约定）
```

> ⚠️ 注意：首次干净回归 `pytest` **collection 失败**——`tests/test_l1_contract.py` 依赖
> `jsonschema`，但 pyproject.toml 的 `[project.optional-dependencies].dev` 未声明。
> 这是**工程缺陷（MAJOR-DEP-005）**；QA 为完成回归手动 `pip install jsonschema`，
> 已如实标注，不掩盖。修复前 Gate 1/9 在干净环境**不可复现**。

## 2. 干净环境全量回归结果（真实运行）

| 项 | 命令 | 结果 |
|---|---|---|
| lint | `ruff check .` | **All checks passed**（0 error） |
| 全量测试 | `pytest -q` | **387 passed / 1 skipped / 1 xfailed / 0 failed**（含 QA 新增 42 + 1 xfail；skip 真实原因=`tests/test_api_v11.py:113` 无 candidate，非 PG 门控） |
| L0 | `benchmark run --level L0` | **36/36（pass_rate 1.0）** |
| legacy v0.2 参考 | L0Runner.run_legacy_file | **20/24（pass_rate 0.833333，与基线一致）** |
| L1 | L1Runner.run(l1_cases.jsonl) | **6/6，rejected=['l1-07-leak']** |
| Claim Binding | `benchmark run --level CLAIM_BINDING` | **34 cases / P 1.0 / R 0.96 / F1 0.979592 / U 1.0 / A 1.0 / Rej 1.0 / MultiEx 0.75 / MultiPar 0.25 / Cov 1.0**（33 PASS + CB-034 KNOWN-LIMIT） |
| demo | `examples/demo_b2b_saas_mvp.py` | **闭环成功**（total_events=40） |
| release zip | `Vencertia_Intelligence_Lab_v1.1.1.zip` | **338 files**，pyproject version=1.1.1 |

## 3. API smoke（Gate 5）

| 路径 | 默认容器（sqlite） | 注入 InMemoryRepository |
|---|---|---|
| GET /health | 200 | 200 |
| POST /v1/solve | **500（BLOCKER-API-001）** | 200 |
| GET /v1/decisions/{id} | —（solve 已 500） | 200 |
| GET /v1/decisions/{id}/sensitivity | — | 200 |
| GET /v1/decisions/{id}/trace | — | 200 |
| GET /v1/evidence/{id}/bindings | — | 200（缺失证据幂等返回空） |
| GET /v1/beliefs/{id}/history | — | 200（缺失幂等返回空） |
| GET /v1/projects/{id}/beliefs | — | 200 |

**结论**：`make api`（文档化默认路径，README:28 / OPERATIONS:110 / Makefile:26）在默认
`sqlite:///data/vencertia.db` 下，**POST /v1/solve 稳定 500**——sqlite 连接在主线程创建、
FastAPI sync 端点在线程池执行，跨线程访问抛 `sqlite3.ProgrammingError`（api.py:475 →
runtime.py:272/820 → base.py:384/263 → sqlite.py:51）。仅注入 InMemoryRepository 时全绿。
**Gate 5 在默认部署路径上不通过。**

## 4. CLI smoke（Gate 6）

| 命令 | 结果 |
|---|---|
| `vencertia solve <req.json>` | ✅ 返回 ABSTAIN 决策（decision_id 生成） |
| `vencertia decision evaluate`（子命令存在） | ✅（--help 可列） |
| `vencertia evidence bind`（子命令存在） | ✅（--help 可列） |
| `vencertia benchmark run --level CLAIM_BINDING` | ✅ 指标正常输出 |
| `vencertia --help` / `benchmark --help` | ✅ |

> 说明：任务描述中的「benchmark binding」实际 CLI 名为 `benchmark run --level CLAIM_BINDING`
> （Makefile `benchmark-binding` 同义），非缺陷。

## 5. OpenAI-compatible adapter（Gate 7，mock HTTP）

httpx MockTransport 实测 8 场景全部符合 ADR-012 映射：
valid structured JSON ✅ / invalid JSON→ProviderInvalidJSONError ✅ /
timeout→ProviderTimeoutError ✅ / 401→ProviderUnavailableError ✅ /
429→ProviderRateLimitError ✅ / 500→ProviderUnavailableError ✅ /
wrong shape→ProviderSchemaMismatchError ✅ / empty→ProviderEmptyResultError ✅。

## 6. HttpSearchProvider + legacy（Gate 7/8）

- HttpSearchProvider 23 条既有测试 + QA 新增 9 条（malformed/timeout 降级/search=None）全部通过。
- Legacy V10.2 migration tests：7 passed（test_legacy_import.py）+ v0.2 参考 20/24 不变。

## 7. 10 项 Release Gate 独立核验

| # | Gate | 工程师声称 | QA 独立核验 | 判定 |
|---|---|---|---|---|
| 1 | pytest 0 failed | ✅ 345/1 | 基环 345/1 ✓；**干净环境 collection 失败（jsonschema 未声明）** | ⚠️ **不通过**（干净环境不可复现；MAJOR-DEP-005） |
| 2 | L0 ≥36/36 | ✅ | 36/36（两环境） | ✅ 通过 |
| 3 | binding 8 指标 | ✅ | 8 指标+Coverage 全数一致 | ✅ 通过 |
| 4 | L1 三层+leakage 拒绝 | ✅ | 6/6 + l1-07-leak 拒绝 | ✅ 通过 |
| 5 | API smoke | ✅ | **默认容器 /v1/solve 500**；仅 InMemory 路径绿 | ❌ **不通过**（BLOCKER-API-001） |
| 6 | CLI smoke | ✅ | solve/decision/evidence/benchmark 可执行 | ✅ 通过 |
| 7 | 三 provider adapter | ✅ | mock/openai_compatible(8 场景)/http(23+9 条) 全过 | ✅ 通过 |
| 8 | legacy PASS | ✅ | migration 7 passed + v0.2 20/24 | ✅ 通过 |
| 9 | CI 等价本地 | ✅ | ruff 0 + pytest（需手动补 jsonschema）+ benchmark + smoke | ⚠️ **不通过**（同 Gate 1 依赖缺口） |
| 10 | 文档数字一致 | ✅ | README/CHANGELOG/IMPLEMENTATION 数字与实测一致 | ✅ 通过 |

**Gate 小结：7/10 通过；Gate 1、5、9 不通过。**

## 8. 遗留问题（本轮新增）

| ID | 严重级 | 文件:行 | 说明 |
|---|---|---|---|
| BLOCKER-API-001 | BLOCKER | src/vencertia/repositories/sqlite.py:51（:43） | `make api` 默认路径 /v1/solve 500（跨线程 sqlite）。见 RC_2 §3 |
| MAJOR-CB-001 | MAJOR | src/vencertia/runtime/claim_binding.py:378 | ambiguity 边界浮点噪声（0.90/0.80 误判 AMBIGUOUS）。见 RC_2 §3 |
| MAJOR-DEP-005 | MAJOR | pyproject.toml dev deps | `jsonschema` 未声明 → 干净环境 test_l1_contract 无法收集，Gate 1/9 不可复现。修复：dev deps 增加 `jsonschema>=4` |
| MINOR-CB-002 / MINOR-PR-003 / MINOR-L1-004 / MINOR-QA-002 | MINOR | 见 RC_2 §3 | 文档/断言精确性问题，不影响数据安全 |

## 9. Final Release Decision（QA 独立结论）

- **结论：NOT READY。**
- 理由：Gate 1/5/9 不通过——① `make api` 默认 sqlite 路径 /v1/solve 500（BLOCKER，
  部署即崩）；② claim_binding ambiguity 边界浮点噪声（MAJOR，语义不一致，与 F6 同源未修）；
  ③ 测试依赖 jsonschema 未声明（MAJOR，干净环境不可复现 Gate 1）。
- 建议：修复上述 3 项后重跑全量回归（预计 +1 轮）；MINOR 项随 RC 文档修订一并处理。
- 工程师的 345 passed / L0 36/36 / benchmark 数字 / 版本 / zip 数：**全部属实**，
  但「10 Gate 全过」的结论**不成立**——其 API smoke 只覆盖注入内存仓库的测试路径，
  未覆盖默认容器接线（这也是 345 绿而真实部署 500 的原因）。
