# Implementation plan — executable sequence

## Phase 0 — completed in this package

1. Freeze the product definition around calibrated decisions, not agents.
2. Create canonical Pydantic contracts for Belief, Evidence, Decision, Experiment and Prediction.
3. Implement deterministic evidence weighting, correlated-source discounting and belief updates.
4. Implement risk/opportunity-cost-aware decision scoring with abstention.
5. Implement decision-critical uncertainty detection and experiment prioritization.
6. Implement calibration metrics (Brier and ECE), SQLite primitive, CLI, API and regression tests.
7. Create L0 synthetic benchmark and integration boundaries.

## Phase 1 — next concrete actions (highest priority)

### 1. Build the real benchmark before adding intelligence
Owner: Intelligence/Eval
Deliverable: `benchmark_v0.2` with 100–200 historical, time-sliced venture decisions.
Actions:
- Define a case schema with T0 context, available evidence, options, reference/gold rationale, future outcome and leakage audit.
- Convert existing internal/user-owned startup cases first; do not scrape labels from future outcomes into T0.
- Double-review 20% of cases; track reviewer disagreement.
- Freeze a test split. Never optimize on it.
Exit gate: ≥100 adjudicated cases; inter-review agreement target defined; leakage checks pass.

### 2. Add a Decision Compiler
Owner: Intelligence
Input: natural-language founder problem + current project state.
Output: objective candidates, decision options, beliefs, unknowns and research tasks using strict schemas.
Implementation: model-agnostic `ReasoningProvider`; route via LiteLLM adapter.
Exit gate: schema validity ≥99%; critical-variable recall measured on benchmark.

### 3. Build Research → Evidence, not Research → Report
Owner: Research
Pipeline: query plan → source retrieval → extraction → claim normalization → provenance → contradiction grouping → evidence objects.
Source hierarchy: direct transaction/behavior/private data > official/primary > reliable secondary > expert > model inference.
Pilot: compare custom web pipeline with GPT Researcher adapter.
Exit gate: evidence precision/recall + contradiction recall exceed baseline at acceptable cost.

### 4. Prediction Ledger in production
Owner: Platform
Every consequential recommendation emits at least one falsifiable time-bound prediction when possible.
Resolution UI/process records actual outcome without rewriting the original prediction.
Exit gate: first 50 resolved predictions; calibration dashboard operational.

## Phase 2 — make the system self-improving

### 5. Component-level optimization with DSPy
Start with evidence classifier and decision compiler. Optimize against frozen train/dev metrics. Never optimize on live test split.
Exit gate: statistically credible metric lift and no calibration regression.

### 6. Retrieval memory
Start with Postgres + lexical/vector support. Introduce Qdrant only if benchmark shows a retrieval gap it solves.
Memory retrieval must be decision-scoped, not “top similar chats”.
Exit gate: decision-relevant context recall improves without unacceptable noise.

### 7. Calibration v2
After sufficient outcomes, fit domain/model-specific calibration: model tag × task × evidence class × venture type. PyMC becomes justified when hierarchical partial pooling adds predictive value.
Exit gate: lower out-of-sample Brier/ECE than global calibration.

## Phase 3 — control-system behavior

### 8. Convergence policy learning
Learn when more research is unlikely to flip a decision. Track marginal value of information, cost and delay.

### 9. Opportunity portfolio
Compare continuing Venture A with Venture B/C or stopping. GO becomes resource allocation, not absolute attractiveness.

### 10. Founder-state dynamics
Runway, energy, access, skill and risk preference are time-varying state variables that change the objective and action policy.

## Weekly operating loop

Monday: freeze candidate changes and benchmark plan.
Tuesday–Wednesday: implement exactly one intelligence change.
Thursday: run offline evaluation, error analysis and cost/latency comparison.
Friday: admit/reject change; deploy accepted version behind a versioned policy; collect prospective predictions/outcomes.

## Definition of done for every iteration

A change is not done because the output “looks better”. It is done when its hypothesis, benchmark slice, metric delta, cost delta, failure modes, version and rollback path are recorded.
