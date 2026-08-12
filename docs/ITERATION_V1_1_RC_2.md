# ITERATION — v1.1 RC Hardening Round 2（QA 对抗 edge-case）

> HISTORICAL SNAPSHOT — 记录 v1.1.1 交付时点事实，不作为 v1.1.2 的 authority。

> 执行人：严过关（QA）· 日期：2026-08-12 · 版本：1.1.1（工作区）
> 基线：docs/ITERATION_V1_1_RC_1.md（工程师实现完成）· 本轮为独立对抗验证，非盖章。

## 1. 独立复跑（trust but verify）

| 项 | 工程师声称 | QA 独立复跑 | 结论 |
|---|---|---|---|
| pytest | 346 collected / 345 passed / 1 skipped / 0 failed | **346 collected / 345 passed / 1 skipped / 0 failed** | ✅ 一致 |
| L0 | 36/36 | **36/36（pass_rate 1.0）** | ✅ 一致 |
| legacy v0.2 参考 | 20/24 不变 | **20/24（pass_rate 0.833333）** | ✅ 一致 |
| L1 | 6/6 + l1-07-leak 拒绝 | **6/6，rejected=['l1-07-leak']** | ✅ 一致 |
| Claim Binding Benchmark | 34 cases：P 1.0 / R 0.96 / F1 0.9796 / U 1.0 / A 1.0 / Rej 1.0 / MultiEx 0.75 / MultiPar 0.25 / Cov 1.0 | **同左**（F1 0.979592），33 PASS + CB-034 KNOWN-LIMIT | ✅ 一致 |
| ruff | 0 error | **All checks passed**（清理我新增测试的 3 个未用 import 后） | ✅ 一致 |
| demo | 闭环 | **成功**（total_events=40，belief/decision/calibration 均输出） | ✅ 一致 |
| 版本 | 1.1.1 | pyproject version=1.1.1；release zip 338 files（核对 make_release） | ✅ 一致 |

> 工程师核心数字**全部真实**，非伪造。测试非橡皮图章——但发现 1 处既有断言为恒真式（见 §3 QA-002）。

## 2. 本轮新增对抗测试（tests/qa_v111/，42 passed + 1 xfailed）

| 文件 | 覆盖边界 | 结果 |
|---|---|---|
| test_qa_v111_binding_edges.py | #1 ambiguity 边界 / #2 rejected vs unbound / #3 旧序列化兼容 / #12 阈值相等 / #13 零预测零gold | 15 passed + **1 xfailed（MAJOR-CB-001）** |
| test_qa_v111_provider_edges.py | #4 malformed payload / #5 timeout 降级 / #6 search=None | 9 passed |
| test_qa_v111_l1_edges.py | #7 旧 case 兼容 / #8 leakage 拒绝 | 4 passed |
| test_qa_v111_sensitivity_edges.py | #9 robustness 阈值边界 / #10 None/inf 不崩 | 8 passed |
| test_qa_v111_benchmark_edges.py | #11/#13/#14/#15 除零 / 极端输入 / 空数据集 | 5 passed |
| test_qa_v111_decision_edges.py | #16 单 option 决策 | 2 passed |

全量回归（含新增）：**387 passed / 1 skipped / 1 xfailed**（346→388 collected，+42）。

## 3. 发现的问题清单

### BLOCKER

| ID | 严重级 | 文件:行 | 复现 | 说明 |
|---|---|---|---|---|
| BLOCKER-API-001 | **BLOCKER** | `src/vencertia/repositories/sqlite.py:51`（根因 `:43` `sqlite3.connect(db_path)` 未设 `check_same_thread=False`） | `python -m uvicorn vencertia.api:app` 后 `POST /v1/solve` → **HTTP 500** `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`（api.py:475 → runtime.py:272 → runtime.py:820 → base.py:384 → base.py:263 → sqlite.py:51） | `make api`（默认 sqlite dsn）下**任何触碰 DB 的端点全 500**（/health 因不碰 DB 而 200）。FastAPI sync 端点跑在 anyio worker 线程，主线程建的 sqlite 连接跨线程使用即炸。现有 API 测试全部注入 `InMemoryRepository`，**从未覆盖默认容器接线** → 345 绿但真实部署路径坏。修复建议：`sqlite3.connect(db_path, check_same_thread=False)`（或按请求建连接）；修复后需补一条「默认容器 + TestClient」的 smoke 测试防回归。 |

### MAJOR

| ID | 严重级 | 文件:行 | 复现 | 说明 |
|---|---|---|---|---|
| MAJOR-CB-001 | MAJOR | `src/vencertia/runtime/claim_binding.py:378` `(reliable[ranked[0]] - reliable[ranked[1]]) < ambiguity_margin` | scores 0.90/0.80、margin=0.10 → `0.90-0.80 == 0.09999999999999998 < 0.10` → 判 **AMBIGUOUS**；而 scores 0.80/0.70 → `0.10000000000000009` → 判 **BOUND**。同一十进制分差 0.10，**取值不同结论相反** | 与 Iteration-1 F6 同类的浮点噪声，但只在 `decision_sensitivity.py` 用 `round(...,6)` 修了，**claim_binding 未修**。实测 8 组常见十进制对中 7 组被误判。修复建议：比较前 `round(top1-top2, 6)`。对应测试以 `xfail(strict=True)` 锁定（test_gap_exactly_equal_to_margin_is_not_ambiguous），修复后会自动转 FAIL 提醒更新。 |

### MINOR

| ID | 严重级 | 文件:行 | 说明 |
|---|---|---|---|
| MINOR-CB-002 | MINOR | `src/vencertia/domain/binding.py:49` | 「UNBOUND remains a compatibility alias for persisted data」言过其实：`BindingStatus.UNBOUND` 只是**名称**别名（value 同为 UNBOUND_EVIDENCE），pydantic **不认字面量 `"UNBOUND"`**——`EvidenceClaimBinding(status="UNBOUND")` 抛 ValidationError。本仓库历史中序列化值一直是 `"UNBOUND_EVIDENCE"`（git 全史确认），故无现存数据损坏；但任何外部旧部署若存过字面量 `"UNBOUND"` 将读不回来。建议：明确文档为「代码级名称别名」；如确需兼容字面量可加 `@field_validator` 归一化。 |
| MINOR-PR-003 | MINOR | `src/vencertia/providers/http_search.py:99-107` | 文档声称「schema mismatch → ProviderSchemaMismatchError」，但 JSON 数组**全为非 dict 元素**（如 `["a", 42]`）时 `_extract_items` 静默过滤为空 → 抛 **ProviderEmptyResultError**。语义上更像 schema mismatch；不影响数据安全（无伪证据），但文档与实际行为有偏差，且该空结果会伪装成「搜索无结果」而非「响应形状错误」。 |
| MINOR-L1-004 | MINOR | `src/vencertia/benchmark/l1.py:133-136` | leakage 门是**标记制**（`leakage_audit_passed` 标志，编写期人工审计），运行时不做 T0 内容扫描。若标志被误置 True 且 T0 含 future 信息，runner 会照跑（已用测试固化该边界行为）。与 ADR-006「flag-based」一致，非代码 bug；但 IMPLEMENTATION_REPORT 第 100 行「leakage_audit_passed != true 的 case 拒绝执行」需明确这是编写期审计责任，非运行时防线。 |
| MINOR-QA-002 | MINOR | `tests/test_http_search_provider.py:315-318` | 工程师既有断言 `assert result.evidence_used == [] or all(eid.startswith("E_") is False or True for eid in result.evidence_used)` 是**恒真式**（`x or True` 永远 True）——橡皮图章断言，未真正验证「失败 provider 零伪证据」。QA 已用独立测试（retrieval=None 时 evidence_used == []）替换验证，语义成立。 |

## 4. 16 类边界逐项结论

| # | 边界 | 结论 |
|---|---|---|
| 1 | ambiguity 分差恰等于 margin | **源码 bug（MAJOR-CB-001）**：浮点噪声导致 0.90/0.80 被误判 AMBIGUOUS |
| 2 | rejected vs unbound 语义 | ✅ scope 违规→REJECTED；无候选→UNBOUND；低于 reject_threshold→UNBOUND（不混） |
| 3 | 旧序列化 status 兼容 | ⚠️ 名称别名可用、字面量 `"UNBOUND"` 不可读（MINOR-CB-002，仓库历史无此数据） |
| 4 | HTTP malformed payload | ✅ 结构对字段错→SCHEMA_MISMATCH；非 dict 数组→EMPTY_RESULT（MINOR-PR-003） |
| 5 | HTTP timeout | ✅ ProviderTimeoutError（ProviderError 子类）→ 运行时 PROVIDER_FAILED 事件 + 零伪证据 |
| 6 | search=None | ✅ solve 不崩，research trace queries=0、evidence_used 空 |
| 7 | L1 旧 case（仅 information_available_at_t0） | ✅ 三字段默认 []，镜像 decision/options，runner 可跑 |
| 8 | L1 leakage | ✅ flag=false 拒绝；flag=true 含 future 信息会照跑（MINOR-L1-004 边界说明） |
| 9 | robustness 阈值恰等 | ✅ 严格 `<` 语义：==fragile→MODERATE、==moderate→ROBUST、==margin→不降档（与 F6 round(6dp) 一致） |
| 10 | sensitivity None/inf | ✅ 无 finite flip→flips=[]、ROBUST、JSON round-trip 正常 |
| 11 | benchmark 除零 | ✅ `_safe_ratio` 零分母→None（渲染 N/A），非伪造 0.0；分母存在时真 0.0 |
| 12 | score 恰等于 threshold | ✅ min_score 含边界（==0.7→BOUND）；reject_threshold 含边界（==0.4 记录为候选） |
| 13 | 零预测 / 零 gold binding | ✅ precision→N/A（tp+fp=0），recall→0.0（tp+fn>0），f1→N/A |
| 14 | all unbound / all ambiguous | ✅ 各自 accuracy 有值，其余 N/A；不崩 |
| 15 | 空 benchmark dataset | ✅ n=0，全 N/A，render 正常 |
| 16 | 单 option 决策 | ✅ 模型层 min_length=1 拦截空 options；单 option 由 DecisionEngine.evaluate 抛 `ValueError: at least two options` |

## 5. 需工程师修复条目

1. **BLOCKER-API-001**（sqlite 跨线程 500）— 阻断 `make api` 默认部署，必须修。
2. **MAJOR-CB-001**（claim_binding 浮点边界）— 与 F6 同源未修，建议 `round(...,6)` 对齐。

## 6. 后续

- ITERATION_V1_1_RC_3.md：干净环境全量回归 + 10 Gate 核验（QA Iteration 3）。
