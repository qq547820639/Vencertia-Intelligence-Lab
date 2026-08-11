# Architecture v0.1

## Product definition

Vencertia is not a multi-agent advisor. It is a decision runtime that continuously maintains a venture belief state, reduces decision-critical uncertainty, and stops researching when additional information is unlikely to change the current decision.

## Non-negotiable invariants

1. LLM output is not ground truth and enters evidence with a low prior weight.
2. Evidence is immutable; beliefs are derived state.
3. Every material decision records the evidence/belief snapshot used at the time.
4. A recommendation may abstain. Forced certainty is a defect.
5. State mutation is deterministic and versionable.
6. A new model/framework must prove incremental benchmark value before production admission.
7. Human values define the objective; algorithms optimize under that objective.

## Core domain objects

- **Objective**: what the founder actually wants to optimize.
- **Belief**: a falsifiable proposition with probability and uncertainty.
- **Evidence**: an observation with provenance, directness, reliability, verification status and independence group.
- **Decision**: options whose utility depends on beliefs and costs.
- **Experiment**: a reversible action intended to reduce a decision-critical uncertainty.
- **Outcome**: what reality produced after an action.
- **Prediction**: time-bound probabilistic claim used for calibration.

## Control loop

```text
Problem
  ↓
Decision compiler (LLM/tool layer)
  ↓
Belief graph ← Evidence ingestion ← Research / private data / experiments
  ↓
Decision engine
  ├─ converged → recommend reversible action
  └─ not converged → uncertainty ranking
                         ↓
                  experiment optimizer
                         ↓
                      outcome
                         ↓
                  belief/calibration update
```

## Three-layer separation

### Reality layer
Web, official data, CRM, email, analytics, transactions, experiment results.

### Intelligence layer
Model routing, research planning, extraction, contradiction detection, structured inference.

### Decision layer — Vencertia IP
Evidence policy, belief update, uncertainty, utility/opportunity cost, experiment value, convergence, prediction ledger, calibration and policy learning.

The decision layer never depends directly on a specific LLM SDK or agent framework.
