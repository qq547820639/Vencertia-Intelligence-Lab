# Vencertia v1.0 — Benchmark

Three layers (ADR-006: benchmark precedes OSS admission).

## L0 — synthetic strategy regression

- Source: `data/benchmarks/l0_cases.json` (26 cases) + `data/benchmarks/v0.2.jsonl` (legacy 24-case reference).
- Covers: GO / KILL / PIVOT / HOLD / CONDITIONAL_GO / SELECT_OPTION / ABSTAIN,
  company-case isolation, transferability eligibility, evidence posterior
  references, NEUTRAL mass, dedup discount, convergence states
  (RESEARCH_MORE / EXPERIMENT_REQUIRED / SEARCH_EXHAUSTED / CONDITIONALLY_CONVERGED /
  CONVERGED / EXECUTE), experiment selection (critical boost, time/cost penalty).
- Run: `make benchmark` or `vencertia benchmark run --level L0`.

Result (iteration 3): **L0 26/26 pass_rate 1.0**. Legacy v0.2 reference:
20/24 — the 4 diverging labels are hand-authored reference labels that do not
match the deterministic engine math (the v0.1 engine itself abstains on those
inputs); the file is preserved as a reference, not a hard gate. Behavior
regression is guaranteed by the new L0 suite + unit tests.

## L1 — historical time-sliced replay

- Source: `data/benchmarks/l1_cases.jsonl` (6 accepted + 1 leakage-rejected case).
- Discipline: only `information_available_at_t0` is injected; `hindsight_data`
  is never fed to the decision. Cases with `leakage_audit_passed != true` are
  rejected by the harness.
- **Leakage gate is flag-based (authoring-time audit, MINOR-L1-004)**:
  `leakage_audit_passed` is set by the case author/reviewer after a manual
  audit (ADR-006). It is NOT a runtime content scan — a case whose flag is
  true but whose T0 envelope accidentally contains future-looking data will
  run. Cases must be audited at authoring time before being added to a frozen
  benchmark.
- Run: `vencertia benchmark run --level L1`.

Result (iteration 3): **L1 6/6 pass_rate 1.0, 1 rejected (leakage)**.

## Metrics

- decision accuracy, selective accuracy, coverage (abstention quality),
  experiment selection accuracy, critical uncertainty accuracy,
  evidence precision/recall/F1, decision regret, Brier, ECE.
- Calibration metrics only count settled predictions (TRUE/FALSE).

## Comparison harness

`comparison_report(baseline, candidate)` produces a baseline-vs-candidate
delta report with an ADMITTED/REJECTED verdict (candidate must not reduce
pass rate).
