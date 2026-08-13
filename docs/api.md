# Vencertia v1.0 — REST API

Base URL: `http://localhost:8000`. All responses use the unified envelope:

```json
{ "code": 0, "data": { ... }, "message": "ok" }
```

Error mapping: `EntityNotFoundError` → 404, `StaleWriteError` → 409,
`ValueError` → 400 (all with `code != 0`).

## Health

### `GET /health`
```json
{ "code": 0, "data": { "ok": true, "version": "1.0.0", "policy_version": "1.0", "model_provider": "mock" }, "message": "ok" }
```

## Decisions

### `POST /v1/decisions/compile`
Body: `{ "project_id": "...", "problem_text": "...", "user_id": "...", "options": [...]? }`
Returns a `CompiledDecision` (Objective + Decision + Claims + Beliefs + Experiments).

### `POST /v1/decisions/evaluate`
Body: `{ "decision_id": "DEC_..." }`
Returns `{ "decision": DecisionResult, "convergence": ConvergenceReport }`.

### `GET /v1/decisions/{id}`
Returns the persisted Decision (with recommendation/confidence/convergence).

## Evidence

### `POST /v1/evidence`
Body: `{ "evidence": { ...Evidence } }` — graded by EvidencePolicy and stored.
Company-case evidence without transferability is gated (never updates project beliefs).

### `POST /v1/evidence/import`（v1.4）
Body: `{ "items": [ { ...Evidence }, ... ], "project_id": "..."? }` — batch import.
Each item runs the full pipeline: dedup → content-fingerprint idempotency → policy grade
→ authority apply → persist. Returns `EvidenceImportReport`
（`total`/`imported`/`deduplicated`/`conflicts`/`bound`/`unbound`/`imported_ids`/
`dropped_ids`/`rejected`）。

## Outcomes

### `POST /v1/outcomes`
Body: `{ "action_id": "ACT_...", "result": "...", "quantitative": {...}?, "outcome_type": "FAILURE" }`
Triggers the closed loop: outcome → evidence → belief → decision re-eval →
prediction settlement → calibration update. Returns `OutcomeRecordedResult`.

## Experiments

### `POST /v1/experiments/propose`
Body: `{ "decision_id": "DEC_...", "candidates": [...], "max_results": 5 }`
Returns `{ decision_insufficient, reason, ranked: [RankedExperiment] }`.

### `POST /v1/experiments/{id}/resolve`
Body: `{ "result": "...", "outcome_type": "SUCCESS" }`
Records the outcome, resolves the experiment, runs the closed loop.

## Predictions

### `POST /v1/predictions`
Body: `{ "decision_id": "DEC_..." }` — registers a snapshot per relevant belief.

### `POST /v1/predictions/{id}/resolve`
Body: `{ "outcome": true|false }` — settles irreversibly; hash mismatch → CANCELLED.

## Calibration

### `GET /v1/calibration?scope=ALL&key=ALL`
Returns `CalibrationProfile` (Brier/ECE/buckets). Scopes: ALL/MODEL/DOMAIN/MODULE.

## Projects

### `GET /v1/projects/{id}/beliefs`
### `GET /v1/projects/{id}/critical-uncertainties`

## Solve

### `POST /v1/solve`
Body: `SolveRequest` → full pipeline:
compile → research → evidence → belief → convergence → evaluate → (ABSTAIN →
experiment) → predictions. Returns `SolveResult`.

Query params (v1.3):
- `view=summary`：返回 5 段合同（`current_judgment` / `rationale` /
  `biggest_unknown` / `next_step` / `change_condition`）+ ABSTAIN 四要素 +
  透明度段；`view=full`（默认）返回完整 `SolveResult`。
- `advanced=true`：默认（`view=full` 且未指定 `advanced`）会剥掉
  `advanced_view`；`advanced=true` 展开结构化 `SolveResultAdvancedView`。

```json
{
  "decision": DecisionResult,
  "decision_id": "DEC_...",
  "convergence": ConvergenceReport,
  "critical_uncertainties": [CriticalUncertainty],
  "next_experiment": RankedExperiment | null,
  "predictions": [PredictionEntry],
  "rationale": [str]
}
```

## Start the server

```bash
make api        # uvicorn vencertia.api:app --port 8000
```
