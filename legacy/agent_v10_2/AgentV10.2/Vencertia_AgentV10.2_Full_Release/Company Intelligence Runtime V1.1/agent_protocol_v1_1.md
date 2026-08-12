# Vencertia Company Intelligence Agent Protocol V1.1

Status: COMPATIBILITY DRAFT  
Depends on: Startup Intelligence Company Case Schema V1.4 + Compatibility Extension V1.1 + Company Intelligence Runtime V1.1

## 1. System-level evidence rule

```text
PROJECT REALITY
> PROJECT DIRECT EVIDENCE
> PROJECT EXPERIMENT RESULTS
> ELIGIBLE COMPANY CASE FACTS
> REVIEWED CASE INTELLIGENCE
> MODEL PRIOR KNOWLEDGE
```

Case Evidence never becomes Project Evidence by analogy.

## 2. Canonical comparison unit

Compare `Company × Business Model Snapshot × Scope` using `CaseUnitRef`, not a company name alone.

## 3. Retrieval objectives

V1.1 retains V1.0 objectives and adds:

```text
COMPANY_DEEP_DIVE
COMPETITIVE_CASE_SET
FOUNDER_MARKET_FIT
```

Use `get_case` for full deep dives and `compare_case_set` for explicit multi-case comparisons. Ordinary specialist context still defaults to `CaseContextPack`.

## 4. Restored V9 structured intelligence

`FounderRecord` is public company-case founder intelligence and remains separate from user Founder Profile/Memory.

`FundingRound` is a structured funding event. Funding may explain capital dependence or financing sequence, but it is not evidence of demand, healthy unit economics, or project validity.

## 5. Eligibility and transferability

Runtime use-specific Eligibility is a hard permission. Before material transfer, use `ComparisonResult`, `CompareCaseSetResult`, or `CaseContextPack` and distinguish `TRANSFERABLE`, `CONDITIONAL`, and `DO_NOT_TRANSFER`.

## 6. Incremental research update

A8 or another authorized research path may submit:

```text
propose_case_update
submit_evidence
refresh_case
```

These are proposals/jobs, not direct database mutation. The deterministic Mutation Engine owns commit authority. `resolve_case_conflict` is review/admin governed.

## 7. Legacy mutation language

Any V9 wording granting direct A8 `WRITE/UPDATE` authority is DEPRECATED for canonical mutation. Interpret it as permission to submit an authorized proposal through Runtime.

## 8. Agent-specific additions

- A0: may authorize deep dive/case set and route refresh/update proposals.
- A1: may use `FOUNDER_MARKET_FIT`; never merge external founder records into user memory.
- A4: may use competitive case sets for adversarial comparison.
- A5: FundingRound is context only; benchmark eligibility remains unchanged.
- A8: owns Company Intelligence interpretation, deep dive, case-set synthesis, and update/evidence proposals; does not own commit authority.
- A10: may use deep dive/case sets for external-readiness calibration while preserving CASE FACT ≠ PROJECT FACT ≠ PROJECT ASSUMPTION.

## 9. Legacy status mapping

Use Compatibility Extension V1.1. Do not continue emitting coarse V9 status values where a V1.4 canonical field exists.
