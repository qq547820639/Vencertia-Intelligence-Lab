# Providers（v1.1.1）

> 版本：1.1.1 · 关联：ADR-009 / ADR-012 · 更新：GAP-02 / GAP-10

## Composition Root

`Settings.model_provider` 决定模型 Provider；`Settings.search_provider`
（GAP-02）独立决定搜索 Provider。`api.py` 与 `cli.py` 共用
`build_container()`（`container.py`），不再各自硬编码 Mock。

```
Settings → Repository Factory → Provider Factory → EngineBundle
        → SolveOrchestrator → FastAPI / typer
```

## Provider 注册表

```python
register_model_provider(name, factory)    # OSS 准入后追加
register_search_provider(name, factory)   # OSS 准入后追加（GAP-02）
create_model_provider(settings)           # mock | openai_compatible | registry
create_search_provider(settings)          # mock | http | registry（GAP-02）
create_retrieval_provider(settings)       # mock → MockRetrievalProvider；否则 None
create_provider_bundle(settings)          # ProviderBundle(model, search, retrieval)
```

### Search Provider 选择（GAP-02）

| `search_provider` | 行为 |
|---|---|
| `mock`（默认） | `MockSearchProvider`，全离线确定性 |
| `http` | `HttpSearchProvider`（通用 HTTP 搜索 adapter，httpx）；**要求 `VENCERTIA_SEARCH_URL` 非空**，否则启动 fail loud（`ProviderUnavailableError`），**禁止静默退回 Mock** |
| 其它/未知 | fail loud（结构化错误），不静默回退 |

**Generic HTTP Search adapter implemented. No commercial search vendor is
bundled. Live use requires user-supplied endpoint and credentials**
（`VENCERTIA_SEARCH_URL` / `VENCERTIA_SEARCH_API_KEY` /
`VENCERTIA_SEARCH_TIMEOUT`）。未集成任何商业搜索服务；外部响应一律
normalize 为内部 `SearchResult`（title/url/snippet/content/published_at/source/
metadata），厂商 DTO 不泄漏进 Domain。

运行期失败（timeout / connection / 401 / 429 / 500 / 非 JSON / malformed JSON /
schema mismatch / empty / partial）→ 结构化 `ProviderError` 族，记录
`PROVIDER_FAILED` 事件并 graceful degradation（研究停止规则诚实声明
`SEARCH_EXHAUSTED`），**不产生伪 Evidence、不修改 canonical 状态、
不 silent fallback mock**。

## 韧性（ADR-012）

`with_resilience(provider, settings)` 包装：捕获
`Timeout / RateLimit / InvalidJSON / SchemaMismatch / Unavailable / Empty / Partial`
→ 指数退避重试（`provider_max_retries=2`）→ 结构化错误（`ProviderError` 族），
不抛裸异常。外部输出一律 Candidate → Validation → 才持久化。

## 可观测性

`CallRecorder` 记录 `ProviderCallRecord`：
`kind / provider / model / request_id / task_kind / latency_ms / tokens / cost /
success / retry_count / error_type`。**红线：不记录 prompt / 敏感内容**。
