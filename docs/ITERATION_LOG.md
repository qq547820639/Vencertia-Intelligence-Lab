# Iteration log

## Iteration 0 — AgentV9 audit
Finding: strong reality/evidence/state principles, but authority was distributed across Orchestrator, Routing, State Transition and specialist prompts. “Agent” was acting as both organizational metaphor and runtime abstraction.
Decision: preserve principles; delete Agent as a domain primitive.

## Iteration 1 — deterministic decision kernel
Built Belief/Evidence/Decision/Experiment/Prediction objects, provenance weighting, belief update, risk-adjusted utility, uncertainty, abstention, calibration, API/CLI and a synthetic smoke benchmark.
Failure found: low-cost experiments were represented as decision options, so the engine could confuse “learn next” with “commit now”.

## Iteration 2 — decision/experiment separation
Separated resource-commitment decisions from information-acquisition experiments. A non-converged decision now abstains and independently selects the highest-value reversible experiment targeting decision-critical uncertainty.
Result on L0 synthetic control-policy regression: 24/24 decision cases pass; selective accuracy 100%; experiment selection on abstentions 100%. This is a software/policy regression result only, not evidence of real-world decision superiority.

## Iteration 3 — calibration and benchmark operations
Added HistoricalDecisionCase schema, JSON Schema export, leakage-audit field, prediction persistence/resolution, calibration CLI and API smoke tests. This turns the next phase—real historical replay and prospective prediction collection—into an operational workflow rather than another prompt rewrite.
