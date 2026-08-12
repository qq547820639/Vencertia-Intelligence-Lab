"""L2Runner — prospective prediction registry and settlement (v1.1).

Prospective predictions are registered BEFORE outcomes are known; settlement
is always manual/human (or OutcomeService) — the system never infers outcomes.
Schema lives at ``data/benchmarks/l2/predictions.jsonl``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from vencertia.domain import PredictionEntry, utcnow
from vencertia.repositories.base import EntityNotFoundError, Repository

# Repository root = parents[3] (benchmark -> vencertia -> src -> repo root)
_REPO_ROOT = Path(__file__).resolve().parents[3]
L2_SCHEMA_PATH = _REPO_ROOT / "data" / "benchmarks" / "l2" / "predictions.jsonl"

L2_FIELDS = [
    "id",
    "project_id",
    "claim_id",
    "target",
    "predicted_probability",
    "registered_at",
    "due_at",
    "outcome",
    "resolved_at",
    "resolution_source",
]


class L2Runner:
    """Prospective prediction lifecycle: register → list due → settle."""

    def __init__(self, repo: Repository | None = None, path: Path | None = None) -> None:
        self.repo = repo
        self.path = path or L2_SCHEMA_PATH

    def register(self, entry: PredictionEntry) -> PredictionEntry:
        """Register a prospective prediction (must be OPEN)."""
        if self.repo is None:
            raise ValueError("L2Runner requires a repository to register predictions")
        if entry.resolution not in ("OPEN", None):
            raise ValueError(f"Prediction {entry.id} is not open; cannot register.")
        self.repo.save_prediction(entry)
        self._append_line(entry)
        return entry

    def settle(self, entry_id: str, outcome: bool, source: str) -> PredictionEntry:
        """Manually settle a due prediction (human/OutcomeService outcome)."""
        if self.repo is None:
            raise ValueError("L2Runner requires a repository to settle predictions")
        entry = self.repo.get_prediction(entry_id)
        if entry is None:
            raise EntityNotFoundError("prediction", entry_id)
        if not entry.is_open:
            raise ValueError(f"Prediction {entry_id} is already settled ({entry.resolution}).")
        settled = entry.model_copy(
            update={
                "resolution": "TRUE" if outcome else "FALSE",
                "outcome": outcome,
                "resolved_at": utcnow(),
                "resolution_source": source,
                "version": entry.version + 1,
            }
        )
        self.repo.save_prediction(settled, expected_version=entry.version)
        self._append_line(settled)
        return settled

    def due_report(self, as_of: datetime | None = None) -> list[PredictionEntry]:
        """List predictions that are due (or overdue) for settlement."""
        if self.repo is None:
            return []
        as_of = as_of or utcnow()
        return [p for p in self._all_open() if p.due_at <= as_of]

    def _all_open(self) -> list[PredictionEntry]:
        return [p for p in self.repo.list_predictions() if p.is_open]

    def _append_line(self, entry: PredictionEntry) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {field: getattr(entry, field) for field in L2_FIELDS if hasattr(entry, field)}
            # registered_at is the L2 schema name for the entry creation time.
            payload["registered_at"] = entry.created_at
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")
        except OSError:  # pragma: no cover - observability must not break flow
            pass
