# Vencertia Intelligence Lab v0.1

A calibration-first decision runtime for high-uncertainty venture building.

This repository is the first executable replacement for the AgentV9 prompt-centric architecture. The core thesis is:

> State → Belief → Evidence → Decision → Experiment → Outcome → Calibration → Updated policy.

## What is already executable

- Bayesian-style belief state using Beta pseudo-counts.
- Evidence provenance weighting with an explicit rule that model inference is weak evidence.
- Correlated-evidence discounting.
- Risk-adjusted option scoring and abstention when the decision has not converged.
- Decision-critical uncertainty detection.
- Experiment ranking by information gain × decision impact × uncertainty / cost-time.
- Prediction ledger primitives and Brier/ECE calibration metrics.
- SQLite persistence primitive.
- FastAPI endpoints and CLI.
- Synthetic policy-regression benchmark and pytest suite.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
vencertia demo
vencertia benchmark --path data/benchmarks/v0.2.jsonl
uvicorn vencertia.api:app --reload
```

API endpoints:
- `GET /health`
- `POST /v1/decide`
- `POST /v1/next-experiment`
- `POST /v1/solve` (decision + experiment selection in one iteration)

## Important boundary

The benchmark in this repo is a **synthetic policy regression suite**, not proof of superior startup decisions. Its job is to detect unintended changes while the real benchmark is assembled from time-stamped historical decisions and later outcomes.

See `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, and `docs/OSS_INTEGRATION_DECISIONS.md`.

## Real benchmark / calibration operations

```bash
vencertia validate-case data/templates/historical_case_template.json
vencertia prediction-add prediction.json --db vencertia.db
vencertia prediction-resolve p1 1 --db vencertia.db
vencertia calibration --db vencertia.db
```

The historical case template has `leakage_audit_passed=false` by default on purpose. A case must be manually audited before it enters a frozen real benchmark.
