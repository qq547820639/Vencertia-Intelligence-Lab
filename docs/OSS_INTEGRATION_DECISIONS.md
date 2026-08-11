# Open-source integration decisions — 2026-08-11

## Adopt now at the boundary

### LiteLLM — model gateway
Role: provider normalization, routing/fallbacks, budgets and model A/B. Do not expose LiteLLM types to the domain layer.
Admission experiment: same benchmark across model/provider routes; compare quality, latency, cost and failure rate.

### LangGraph — optional workflow runtime
Role: durable stateful execution, checkpoints, loops and interrupts. Domain state remains Vencertia Pydantic objects; LangGraph is not the canonical data model.
Admission experiment: compare against a simple Python state machine on crash recovery, observability and complexity.

### Ragas — external evaluation toolkit
Role: retrieval/agentic metrics and experiment harness where its metrics match the component being tested. Vencertia retains its own domain metrics such as calibration/regret.

## Pilot after benchmark data exists

### DSPy
Role: optimize structured inference modules against explicit metrics instead of hand-editing long prompts. Start with evidence extraction/classification, not the full decision engine.

### GPT Researcher
Role: candidate research planner/retriever. Consume its sources/evidence, not its final report as truth. Benchmark against a smaller custom research pipeline.

### Qdrant
Role: hybrid dense+sparse retrieval and reranking when Postgres/pgvector or lexical retrieval stops meeting recall/latency needs. Do not introduce it preemptively.

### PyMC
Role: hierarchical calibration and richer belief models after enough resolved predictions/outcomes exist. v0.1 uses transparent Beta pseudo-counts so behavior is inspectable.

## Explicit non-decision

Do not adopt a multi-agent “crew” framework merely to simulate roles. The product is a calibrated control loop, not a meeting between personas.
