# OSS / Model Admission Policy (v1.0, executable)

Derived from `docs/oss-integration-decisions.md` and ADR-006.

## Rule

Any new model/OSS integration (LiteLLM, LangGraph, Qdrant, DSPy, PyMC, new
provider…) must pass the frozen benchmark before production admission.
Admission requires at least one of:

1. Statistically credible quality improvement (no unacceptable cost/latency);
2. Same quality at materially lower cost/latency;
3. A genuinely new required capability with no key-metric regression.

## Process

1. Implement the integration as an **adapter** behind `providers/` interfaces
   (`ModelProvider` / `SearchProvider` / `RetrievalProvider`) — never inside
   the domain or engines (ADR-005).
2. Run the comparison harness:
   `comparison_report(baseline, candidate)` — candidate pass rate must be
   ≥ baseline pass rate (L0; L1 when data allows).
3. Freeze the benchmark set; do not tune the harness to fit a candidate.
4. Update `docs/changelog.md` with the benchmark delta.

## Leakage discipline

- L1 cases must carry `leakage_audit_passed: true`; the harness rejects
  anything else.
- `hindsight_data` is never injected into T0 decisions.

## Vector/retrieval note

v1.0 ships only the `RetrievalProvider` interface + mock. No vector dependency
is allowed without passing this policy (ADR-006).
