# L2 Prospective Prediction Registry

Prospective predictions are registered BEFORE outcomes are known and settled
only by a human / OutcomeService — the system never infers outcomes.

## Schema (`predictions.jsonl`)

One JSON object per line with the following fields:

| field                  | type     | meaning                                          |
|------------------------|----------|--------------------------------------------------|
| `id`                   | str      | prediction id (PRD_...)                          |
| `project_id`           | str      | owning project                                   |
| `claim_id`             | str|null | claim being predicted                            |
| `target`               | str      | natural-language target statement                |
| `predicted_probability`| float    | registered probability (0..1)                    |
| `registered_at`        | datetime | registration timestamp (UTC)                     |
| `due_at`               | datetime | settlement due date (UTC)                        |
| `outcome`              | bool|null| manually recorded outcome (null until settled)   |
| `resolved_at`          | datetime | settlement timestamp (null until settled)        |
| `resolution_source`    | str|null | outcome_id / evidence_id / user                  |

Settlement is immutable for the registered probability; corrections create a
new version (`corrected=true`) per v1.1 `PredictionLedger.correct()`.
