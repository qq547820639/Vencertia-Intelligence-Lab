"""L2Runner — prospective prediction registry and settlement (v1.1).

Prospective predictions are registered BEFORE outcomes are known; settlement
is always manual/human (or OutcomeService) — the system never infers outcomes.
The canonical registry lives at ``data/benchmarks/l2/predictions.jsonl``
(override with ``VENCERTIA_L2_REGISTRY_PATH``).

v1.9 semantics: the JSONL file is a true one-row-per-entry registry — a
settlement REWRITES the entry's row (instead of appending a stale duplicate),
and re-registering an existing id is a no-op on the file side.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from vencertia.domain import PredictionEntry, utcnow
from vencertia.repositories.base import EntityNotFoundError, Repository

_logger = logging.getLogger("vencertia.benchmark.l2")


def _default_registry_path() -> Path:
    """Registry file location.

    ``VENCERTIA_L2_REGISTRY_PATH`` (when set) wins; otherwise the repo-root
    data path is used. The env override exists because the repo-relative
    default is only valid in a source checkout, and so CI/installed runs can
    point the registry away from the tracked file.
    """
    env = os.environ.get("VENCERTIA_L2_REGISTRY_PATH")
    if env:
        return Path(env)
    # Repository root = parents[3] (benchmark -> vencertia -> src -> repo root)
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "benchmarks" / "l2" / "predictions.jsonl"


L2_SCHEMA_PATH = _default_registry_path()

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
        self._upsert_line(entry)
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
        self._upsert_line(settled)
        return settled

    def due_report(self, as_of: datetime | None = None) -> list[PredictionEntry]:
        """List predictions that are due (or overdue) for settlement."""
        if self.repo is None:
            return []
        as_of = as_of or utcnow()
        return [p for p in self._all_open() if p.due_at <= as_of]

    def _all_open(self) -> list[PredictionEntry]:
        return [p for p in self.repo.list_predictions() if p.is_open]

    def _upsert_line(self, entry: PredictionEntry) -> None:
        """Write/refresh the entry's row in the JSONL registry.

        One row per entry id: an existing row (OPEN → settled) is REPLACED in
        place instead of appending a duplicate, and an id already present
        during register is not duplicated. Registry write failures are logged
        (observability must not break the settlement flow), never silent.
        """
        payload = {field: getattr(entry, field) for field in L2_FIELDS if hasattr(entry, field)}
        # registered_at is the L2 schema name for the entry creation time.
        payload["registered_at"] = entry.created_at
        line = json.dumps(payload, default=str, ensure_ascii=False)

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            rows: list[dict] = []
            if self.path.exists():
                for existing in self.path.read_text(encoding="utf-8").splitlines():
                    if not existing.strip():
                        continue
                    try:
                        rows.append(json.loads(existing))
                    except json.JSONDecodeError:
                        # A corrupt line is preserved verbatim rather than
                        # silently dropped (audit surface), then the entry is
                        # appended as a new row below.
                        rows.append({"__raw__": existing})
            replaced = False
            out_lines: list[str] = []
            for row in rows:
                if row.get("id") == entry.id:
                    out_lines.append(line)
                    replaced = True
                elif "__raw__" in row:
                    out_lines.append(row["__raw__"])
                else:
                    out_lines.append(json.dumps(row, default=str, ensure_ascii=False))
            if not replaced:
                out_lines.append(line)
            self.path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        except OSError:
            _logger.warning("L2 registry write failed for %s (%s)", entry.id, self.path)
