"""Prediction Ledger: registered predictions with tamper-evident snapshots."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import PredictionResolution, VencertiaBaseModel, utcnow


class PredictionEntry(VencertiaBaseModel):
    id: str  # PRD_...
    project_id: str
    claim_id: str | None = None
    target: str
    predicted_probability: float = Field(gt=0, lt=1)
    belief_snapshot: dict = Field(default_factory=dict)
    context_snapshot_hash: str = ""
    policy_version: str = "1.0"
    model_tag: str = "default"
    domain: str = "general"
    module_tag: str = "decision"
    due_at: datetime = Field(default_factory=utcnow)
    resolution: PredictionResolution = PredictionResolution.OPEN
    resolved_at: datetime | None = None
    outcome: bool | None = None
    snapshot_verified: bool | None = None
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1

    @property
    def is_open(self) -> bool:
        return self.resolution == PredictionResolution.OPEN.value or self.resolution == "OPEN"

    @property
    def is_settled(self) -> bool:
        return self.resolution in ("TRUE", "FALSE")
