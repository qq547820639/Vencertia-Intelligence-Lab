# Vencertia Company Intelligence Agent Protocol V1.0

Status: DRAFT  
Depends on: Startup Intelligence Company Case Schema V1.4 + Company Intelligence Runtime Protocol V1.0

## 1. System-level rule

All A0–A10 agents treat Company Intelligence as an external case-evidence layer, not as project evidence.

Priority:

```text
PROJECT REALITY
> PROJECT DIRECT EVIDENCE
> PROJECT EXPERIMENT RESULTS
> ELIGIBLE COMPANY CASE FACTS
> REVIEWED CASE INTELLIGENCE
> MODEL PRIOR KNOWLEDGE
```

A case may calibrate reasoning. A case may not upgrade the user's project evidence level.

## 2. Mandatory retrieval trigger

An agent SHOULD request Company Intelligence when at least one is true:

- a material recommendation depends on whether a business pattern has worked or failed elsewhere;
- the agent is comparing venture designs, pricing, GTM, economics, cashflow, delivery, pivot, failure, or restructuring patterns;
- the user explicitly asks for comparable companies/cases;
- a project assumption can be materially calibrated with an eligible benchmark;
- the Project Prosecutor needs disconfirming cases;
- an Agent conclusion would otherwise rely mainly on generic model priors.

An agent SHOULD NOT retrieve merely to decorate an answer with company names.

## 3. Query construction rule

Agents do not issue free-form “find similar companies” requests.

They construct `SearchCasesRequest` with:

- one `retrieval_objective`;
- the current `project_id`;
- only known project dimensions;
- explicit unknowns left absent/unknown rather than invented;
- relevant case roles;
- counterexamples enabled for material decisions.

## 4. Case Unit rule

Agents compare:

```text
Company × Snapshot × Scope
```

not company names.

Any benchmark or analogy must preserve the returned CaseUnitRef.

## 5. Eligibility rule

Eligibility returned by Runtime is authoritative for use permission.

Examples:

- `financial_benchmark_ready = false` → may not be used as a formal financial benchmark;
- `pricing_benchmark_ready = false` → may not calibrate current price as a formal benchmark;
- `gtm_benchmark_ready = false` → may not be presented as validated GTM precedent;
- `failure_benchmark_ready = true` → may be used by A4 for failure-pattern analysis.

Agents do not override Eligibility because a case “looks relevant.”

## 6. Comparison rule

Before a case materially affects an answer, use `ComparisonResult` or a Runtime-built `CaseContextPack`.

Reasoning must consider both:

- similarities;
- critical differences.

Critical differences may invalidate transfer even when semantic similarity is high.

## 7. Transferability rule

For each material case-derived recommendation, distinguish internally:

```text
TRANSFERABLE
CONDITIONAL
DO_NOT_TRANSFER
```

Do not transfer:

- mature-stage growth rate to validation-stage projects;
- founder network advantage to founders without that network;
- one geography's regulatory economics to another without support;
- company-wide margin to a different Revenue Stream;
- old prices as current prices;
- metrics whose definitions are not comparable.

## 8. Counterexample rule

For material decisions, agents SHOULD use paired retrieval when available:

```text
success / durable case
+
failure / anti-pattern / pivot / restructuring case
```

A4 Project Prosecutor SHOULD prioritize disconfirming cases.

## 9. Traceability rule

If a case-derived fact materially changes the recommendation, preserve:

```text
company_id
snapshot_id
claim_id
evidence_id
source_id
last_verified_at
```

Use `get_claim_trace` when provenance or conflict matters.

## 10. Conflict rule

If returned cases disagree:

- do not average away the disagreement;
- identify the differing scope, time, business model, customer, geography, or evidence quality when possible;
- if unresolved, preserve uncertainty.

## 11. Agent-specific use

### A0 Orchestrator
Objectives: GENERAL_RECOMMENDATION, BUSINESS_MODEL, FAILURE_PATTERN.  
Use at major decision points and cross-agent synthesis. Do not mutate the database.

### A1 Founder Diagnosis
Use sparingly for founder-dependency or founder-advantage sensitivity. Never infer venture validity from founder similarity.

### A2 Market Opportunity
Objectives: MARKET_PATTERN, INITIAL_WEDGE, FAILURE_PATTERN.  
Ask whether comparable demand/payment patterns occurred and under what conditions.

### A3 Venture Design
Objectives: BUSINESS_MODEL, INITIAL_WEDGE, PRICING, EARLY_GTM.  
Use cases to generate/calibrate designs, not clone a company.

### A4 Project Prosecutor
Objectives: FAILURE_PATTERN, ANTI_PATTERN, PIVOT_PATTERN, CONTRACT_RISK.  
Prioritize counterexamples and hidden dependencies.

### A5 Financial & Business Model
Objectives: FINANCIAL_BENCHMARK, PRICING, CASHFLOW, CONTRACT_RISK, OPERATING_LEVERAGE.  
Hard-enforce use-specific Eligibility and metric comparability.

### A6 Execution Strategy
Objectives: EARLY_GTM, SCALED_GTM, DELIVERY_MODEL, INITIAL_WEDGE.  
Never infer early GTM from mature acquisition channels.

### A7 Next Action Planner
Retrieve only when a case helps resolve the current Primary Bottleneck. Do not let analogy replace current-project action evidence.

### A8 Startup Case Intelligence
Full read/search/compare/trace access. Still subject to Scope, Time, Eligibility, Evidence, Transferability and write-authority rules.

### A9 Founder Matchmaking
Use only for resource/dependency patterns. Company-case similarity does not determine human match ranking by itself.

### A10 Business Plan Architect
Use eligible cases to calibrate claims and benchmarks. Keep CASE FACT, PROJECT FACT, and PROJECT ASSUMPTION separate.

## 12. User-visible response behavior

When case intelligence materially informs the answer, communicate:

- what pattern the cases support;
- what material difference limits transfer;
- what the user still needs to validate directly.

Avoid “Company X succeeded this way, therefore you should do the same.”

Preferred form:

> Comparable cases support X under conditions A/B. However, your project differs on C, so X should be treated as a testable hypothesis rather than a proven answer. The next direct validation should be Y.

## 13. Write authority

A0–A10 business agents have READ/PROPOSE only.

They may emit an ingestion or mutation proposal, but the canonical database is changed only by the Company Intelligence Mutation Engine after schema, entity, conflict, revision, permission, and audit checks.
