# Vencertia Intelligence Benchmark

## Purpose

Prevent architecture-by-vibes. Every change must be measured against a frozen dataset and a named metric.

## Benchmark layers

### L0 — deterministic unit/policy regression (included now)
Tests evidence weighting, abstention, uncertainty identification and decision policy. Synthetic and intentionally limited.

### L1 — historical decision replay
A case includes only information available at T0, a concrete decision, later observed outcome, and expert/reference decision where available. Leakage from future information is prohibited.

### L2 — component benchmarks
- source retrieval recall/precision
- evidence extraction precision/recall
- claim-source entailment / faithfulness
- duplicate/independence detection
- belief update calibration
- experiment ranking quality
- decision selective accuracy

### L3 — live prospective benchmark
Freeze predictions before outcomes occur. Resolve them later. Measure calibration and realized decision utility.

## Core metrics

- Decision accuracy (when a gold/reference is meaningful)
- Selective accuracy = accuracy only on cases where system chose to decide
- Decision coverage = fraction not abstained
- Brier score for probabilistic predictions
- Expected calibration error (ECE)
- Evidence precision / recall
- Research source diversity and contradiction recall
- Decision-changing evidence recall
- Cost and latency per resolved decision
- Realized regret / opportunity cost where measurable

## Admission rule for an OSS/model integration

Ship only if a frozen evaluation shows one of:
1. statistically credible quality gain without unacceptable cost/latency;
2. same quality at materially lower cost/latency;
3. a new required capability without degrading critical metrics.

No integration is permanent; all are adapters and can be removed.
