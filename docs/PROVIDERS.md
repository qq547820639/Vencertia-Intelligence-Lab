# Providers（v1.1）

> 版本：1.1 · 关联：ADR-009 / ADR-012 · 施工：T01

## Composition Root

`Settings.model_provider` 决定运行时 Provider；`api.py` 与 `cli.py` 共用
`build_container()`（`container.py`），不再各自硬编码 Mock。

```
Settings → Repository Factory → Provider Factory → EngineBundle
        → SolveOrchestrator → FastAPI / typer
```

## Provider 注册表

```python
register_model_provider(name, factory)   # OSS 准入后追加
create_model_provider(settings)          # mock | openai_compatible | registry
create_search_provider(settings)         # mock → MockSearchProvider；否则 None
create_retrieval_provider(settings)      # mock → MockRetrievalProvider；否则 None
create_provider_bundle(settings)         # ProviderBundle(model, search, retrieval)
```

> 真实 Web Search：**Adapter implemented, live provider unavailable without
> credentials** —— 非 mock 配置下 `search=None`，solve 研究轮不调用外部 API。

## 韧性（ADR-012）

`with_resilience(provider, settings)` 包装：捕获
`Timeout / RateLimit / InvalidJSON / SchemaMismatch / Unavailable / Empty / Partial`
→ 指数退避重试（`provider_max_retries=2`）→ 结构化错误（`ProviderError` 族），
不抛裸异常。外部输出一律 Candidate → Validation → 才持久化。

## 可观测性

`CallRecorder` 记录 `ProviderCallRecord`：
`kind / provider / model / request_id / task_kind / latency_ms / tokens / cost /
success / retry_count / error_type`。**红线：不记录 prompt / 敏感内容**。
