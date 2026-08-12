"""ConflictEngine — explicit evidence contradiction detection (v1.1).

When supporting and contradicting evidence both exceed a weight threshold for
the same claim, a persistent EvidenceConflict is created and the belief's
uncertainty is raised (``conflict_uncertainty_raise``).
"""

from __future__ import annotations

from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    ConflictType,
    Direction,
    Evidence,
    EvidenceConflict,
    utcnow,
)


class ConflictEngine:
    """Detects conflicts and applies them to beliefs (uncertainty raise)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def detect(
        self,
        evidence_by_claim: dict[str, list[Evidence]],
        threshold: float = 0.3,
    ) -> list[EvidenceConflict]:
        conflicts: list[EvidenceConflict] = []
        for claim_id, evidence_list in evidence_by_claim.items():
            support_ids: list[str] = []
            contradict_ids: list[str] = []
            support_weight = 0.0
            contradict_weight = 0.0
            for evidence in evidence_list:
                direction = (
                    evidence.supports_or_contradicts.value
                    if hasattr(evidence.supports_or_contradicts, "value")
                    else str(evidence.supports_or_contradicts)
                )
                weight = self._weight(evidence)
                if direction == Direction.SUPPORTS.value:
                    support_ids.append(evidence.id)
                    support_weight += weight
                elif direction == Direction.CONTRADICTS.value:
                    contradict_ids.append(evidence.id)
                    contradict_weight += weight
            if support_weight >= threshold and contradict_weight >= threshold:
                severity = min(1.0, (support_weight + contradict_weight) / 2.0)
                conflicts.append(
                    EvidenceConflict(
                        id="ECF_" + uuid4().hex,
                        claim_id=claim_id,
                        evidence_ids=support_ids + contradict_ids,
                        conflict_type=ConflictType.DIRECT_CONTRADICTION,
                        severity=round(severity, 6),
                        resolution_status="OPEN",
                        created_at=utcnow(),
                    )
                )
        return conflicts

    def apply_to_belief(self, belief: Belief, conflict: EvidenceConflict) -> Belief:
        """Raise belief uncertainty proportional to conflict severity."""
        raise_amount = round(min(1.0, 0.15 * conflict.severity), 6)
        new_uncertainty = round(min(1.0, belief.uncertainty + raise_amount), 6)
        updated = belief.model_copy(
            update={
                "uncertainty": new_uncertainty,
                "confidence": max(0.0, min(1.0, 1.0 - new_uncertainty)),
                "updated_at": utcnow(),
                "version": belief.version + 1,
            }
        )
        # Attach the raise amount for BeliefUpdateRecord bookkeeping.
        object.__setattr__(updated, "_conflict_raise", raise_amount)
        return updated

    @staticmethod
    def _weight(evidence: Evidence) -> float:
        return float(evidence.strength or 0.5) * float(evidence.reliability or 0.5)
