# Vencertia v1.0 — CLI

All commands are non-interactive and parameterized. Rich tables/JSON output.

```bash
# Full solve loop from a request JSON file
vencertia solve <request.json>

# Compile a decision from a problem JSON
vencertia decision compile <problem.json>

# Evaluate a decision from a JSON (decision + beliefs inline)
vencertia decision evaluate <decision.json>

# Add evidence (graded by EvidencePolicy)
vencertia evidence add <evidence.json>

# Batch import evidence from a JSON array / JSONL file (v1.4)
vencertia evidence import <evidence.jsonl> [--project <project_id>]

# Propose experiments for a decision
vencertia experiment propose <decision_id>

# Record an outcome (closed loop)
vencertia outcome record <action_id> <result> [--outcome-type FAILURE]

# Create / resolve predictions
vencertia prediction create <decision_id>
vencertia prediction resolve <prediction_id> <0|1>

# Calibration report (Chinese verdict / brier_zh / ece_zh)
vencertia calibration report [--scope MODEL] [--key gpt-4o]

# One-shot quick-solve on an in-memory store (v1.4, 5-section summary output)
vencertia quick-solve [--problem "..."] [--options-json '...']

# Benchmarks
vencertia benchmark run --level L0
vencertia benchmark run --level L1

# Project beliefs / critical uncertainties
vencertia project beliefs <project_id>
vencertia uncertainties <project_id>

# V10.2 import (read-only on source)
vencertia migrate-v10.2 --source <release-dir> [--dry-run]

# Built-in demo
vencertia demo
```

Every command accepts `--db <path>` to point at a specific SQLite database.
