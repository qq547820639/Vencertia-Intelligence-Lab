# Vencertia Intelligence Lab — delivery report

## Delivered

A runnable v0.1 decision-control kernel that replaces the AgentV9 multi-agent center of gravity with a calibration-first runtime.

Core loop:

`Decision → Beliefs → Evidence → Convergence check → (decide | experiment) → Outcome → Calibration`

The package contains:
- executable Pydantic domain contracts;
- deterministic Evidence Engine with provenance and correlation discounting;
- Belief update and uncertainty;
- Decision Engine with risk, irreversible cost, opportunity cost and abstention;
- Experiment Optimizer targeted at decision-critical uncertainty;
- Prediction Ledger persistence plus Brier/ECE calibration;
- FastAPI and CLI interfaces;
- L0 benchmark harness and 24 synthetic policy-regression cases;
- historical-case schema/template for the real benchmark;
- migration map from all AgentV9 roles to the new architecture;
- OSS integration admission policy.

## Verification at delivery

- pytest: all tests passing.
- L0 decision regression: 24/24.
- selective decision accuracy on L0: 100%.
- experiment selection on L0 abstentions: 100%.
- demo behavior: evidence remains insufficient for a six-week MVP commitment; WTP is detected as the critical uncertainty; paid concierge pilot is selected as the next experiment.

## What is intentionally not claimed

The synthetic benchmark does not demonstrate that Vencertia makes superior real startup decisions. Real calibration requires time-sliced historical cases and prospective predictions resolved against later outcomes. The repository includes the schema and operational path to collect that evidence.

## OSS decisions

Use external projects as replaceable adapters, not the domain core:
- LiteLLM: model gateway candidate.
- LangGraph: optional durable workflow runtime.
- Ragas: component-evaluation toolkit.
- DSPy: later optimization of structured inference modules.
- GPT Researcher: research-pipeline candidate, with outputs converted to Evidence rather than accepted as truth.
- Qdrant: only when benchmarked retrieval needs exceed simpler storage.
- PyMC: later hierarchical calibration after enough outcomes exist.

## Immediate production sequence

1. Populate 100–200 leakage-audited historical cases using `data/templates/historical_case_template.json`.
2. Freeze train/dev/test splits.
3. Implement the natural-language Decision Compiler behind `ReasoningProvider` and benchmark schema validity + critical-variable recall.
4. Implement Research→Evidence and benchmark evidence precision/recall and contradiction recall.
5. Start prospective Prediction Ledger collection from day one.
6. Add LiteLLM/LangGraph/Ragas only behind adapter boundaries and retain only measured improvements.
7. Introduce DSPy/Qdrant/PyMC only after the corresponding data/benchmark gate is met.
