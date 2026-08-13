"""PredictionLedger — register first, settle later, tamper-evident snapshots.

Each entry stores a belief_snapshot dict and a SHA-256 ``context_snapshot_hash``
computed at registration from the entry's own snapshot content. Settlement is
irreversible (original probability never changes); a hash mismatch marks the
entry CANCELLED and raises a warning (docs/calibration.md §7).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import warnings
from datetime import timedelta
from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import Belief, Decision, PredictionEntry, PredictionResolution, utcnow
from vencertia.repositories.base import EntityNotFoundError, Repository

HORIZON_DAYS = {"short": 30, "medium": 90, "long": 180}


class PredictionLedger:
    """Snapshot + settlement service for registered predictions."""

    def __init__(
        self,
        repo: Repository,
        settings: Settings | None = None,
        policy_version: str | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings or get_settings()
        self.policy_version = policy_version or self.settings.policy_version

    # -- registration ---------------------------------------------------------

    def register(
        self,
        decision: Decision,
        beliefs: list[Belief],
        *,
        domain: str = "general",
        model_tag: str = "default",
        module_tag: str = "decision",
    ) -> list[PredictionEntry]:
        """Register one prediction per decision-relevant belief.

        The belief snapshot is frozen at registration; later belief changes do
        not alter it. The context hash is computed from the snapshot itself.

        M0-4: this method does NOT persist. It backfills domain/model_tag/
        module_tag onto each entry and returns them; the caller is responsible
        for persisting exactly once (fresh insert, no expected_version).
        """
        horizon_days = HORIZON_DAYS.get(decision.horizon, 30)
        entries: list[PredictionEntry] = []
        for belief in beliefs:
            if not (belief.decision_relevant or belief.id in decision.relevant_belief_ids):
                continue
            entry = PredictionEntry(
                id="PRD_" + uuid4().hex,
                project_id=decision.project_id,
                claim_id=belief.claim_id,
                target=belief.statement,
                predicted_probability=round(belief.probability, 6),
                belief_snapshot={
                    belief.id: {
                        "probability": belief.probability,
                        "uncertainty": belief.uncertainty,
                        "alpha": belief.alpha,
                        "beta": belief.beta,
                    }
                },
                policy_version=self.policy_version,
                domain=domain,
                model_tag=model_tag,
                module_tag=module_tag,
                due_at=belief.updated_at + timedelta(days=horizon_days),
            )
            entry.context_snapshot_hash = self._entry_hash(entry)
            entries.append(entry)
        return entries

    # -- settlement ------------------------------------------------------------

    def resolve(
        self,
        entry_id: str,
        outcome: bool,
        resolution_source: str | None = None,
    ) -> PredictionEntry:
        entry = self.repo.get_prediction(entry_id)
        if entry is None:
            raise EntityNotFoundError("prediction", entry_id)
        if not entry.is_open:
            raise ValueError(f"Prediction {entry_id} is already settled ({entry.resolution}).")

        verified = self.verify_snapshot(entry)
        resolved_at = entry.resolved_at or utcnow()  # aware UTC settlement timestamp
        if verified:
            resolution = PredictionResolution.TRUE.value if outcome else PredictionResolution.FALSE.value
            resolved_outcome: bool | None = outcome
        else:
            warnings.warn(
                f"Prediction {entry_id} snapshot hash mismatch — marked CANCELLED.",
                RuntimeWarning,
                stacklevel=2,
            )
            resolution = PredictionResolution.CANCELLED.value
            resolved_outcome = None
        updated = entry.model_copy(
            update={
                "resolution": resolution,
                "outcome": resolved_outcome,
                "resolved_at": resolved_at,
                "snapshot_verified": verified,
                "resolution_source": resolution_source,
                "version": entry.version + 1,
            }
        )
        self.repo.save_prediction(updated, expected_version=entry.version)
        return updated

    def correct(self, entry_id: str, new_outcome: bool, source: str) -> PredictionEntry:
        """Create a corrected NEW version of a settled prediction (v1.1).

        The original record is preserved under its own id (immutable); the new
        version gets a fresh id, ``corrected=True`` and the correction source.
        """
        entry = self.repo.get_prediction(entry_id)
        if entry is None:
            raise EntityNotFoundError("prediction", entry_id)
        if not entry.is_settled:
            raise ValueError(f"Prediction {entry_id} is not settled; cannot correct an open entry.")
        new_id = f"{entry.id}#v{entry.version + 1}"
        corrected = entry.model_copy(
            update={
                "id": new_id,
                "resolution": PredictionResolution.TRUE.value
                if new_outcome
                else PredictionResolution.FALSE.value,
                "outcome": new_outcome,
                "resolved_at": utcnow(),
                "snapshot_verified": entry.snapshot_verified,
                "resolution_source": source,
                "corrected": True,
                "version": entry.version + 1,
            }
        )
        # New id → fresh record; the original entry is untouched.
        self.repo.save_prediction(corrected)
        return corrected

    def verify_snapshot(
        self,
        entry: PredictionEntry,
        decision: Decision | None = None,
        beliefs: list[Belief] | None = None,
    ) -> bool:
        """Verify the stored hash; optionally cross-check against live beliefs.

        - Self-contained: recompute the entry hash and compare with the stored
          ``context_snapshot_hash`` (detects tampering of stored data).
        - Cross-check: if ``beliefs`` are supplied, the belief_snapshot must
          match them exactly (detects context drift since registration).
        """
        expected = self._entry_hash(entry)
        if not hmac.compare_digest(expected, entry.context_snapshot_hash or ""):
            return False
        if beliefs:
            snapshot = entry.belief_snapshot or {}
            for belief in beliefs:
                snap = snapshot.get(belief.id)
                if snap is None:
                    continue
                if (
                    abs(float(snap.get("probability", -1)) - belief.probability) > 1e-9
                    or abs(float(snap.get("alpha", -1)) - belief.alpha) > 1e-9
                    or abs(float(snap.get("beta", -1)) - belief.beta) > 1e-9
                ):
                    return False
        return True

    # -- hashing ----------------------------------------------------------------

    def _entry_hash(self, entry: PredictionEntry) -> str:
        payload = {
            "belief_snapshot": entry.belief_snapshot,
            "policy_version": entry.policy_version,
            "target": entry.target,
            "predicted_probability": entry.predicted_probability,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    def _context_hash(self, decision: Decision, beliefs: list[Belief]) -> str:
        """Optional external context hash (used for cross-checks by callers)."""
        payload = {
            "decision_id": decision.id,
            "decision_question": decision.decision_question,
            "options": [o.id for o in decision.options],
            "beliefs": [
                {
                    "id": b.id,
                    "probability": b.probability,
                    "uncertainty": b.uncertainty,
                    "alpha": b.alpha,
                    "beta": b.beta,
                }
                for b in sorted(beliefs, key=lambda x: x.id)
            ],
            "policy_version": self.policy_version,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
