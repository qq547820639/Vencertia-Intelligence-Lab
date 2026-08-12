# Implementation Report Template

Fill one section per engineering iteration.

## Iteration {N} — {date}

### Assumptions
- ...

### Benchmark slice
- L0: new suite `n=26, passed=…, pass_rate=…`; legacy reference `n=24, passed=…`
- L1: `n=…, passed=…, rejected=…`

### Metrics delta vs previous iteration
| Metric | previous | current | delta |
|---|---|---|---|
| test count | | | |
| pass rate | | | |
| L0 pass_rate | | | |
| Brier (demo) | | | |

### Cost / effort
- Files touched, lines changed, time-box notes.

### Failure modes observed
- ...

### Version & rollback
- Commit/version; rollback path (git revert / feature flag).
