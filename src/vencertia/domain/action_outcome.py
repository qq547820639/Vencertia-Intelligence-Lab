"""Action + Outcome: real-world execution and observation."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import ActionStatus, OutcomeType, VencertiaBaseModel, utcnow


class Action(VencertiaBaseModel):
    id: str  # ACT_...
    project_id: str
    kind: str = "OTHER"  # EXECUTE | EXPERIMENT | RESEARCH | OUTREACH | OTHER
    description: str = ""
    decision_id: str | None = None
    experiment_id: str | None = None
    status: ActionStatus = ActionStatus.PLANNED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1


class Outcome(VencertiaBaseModel):
    id: str  # OUT_...
    action_id: str
    observed_at: datetime = Field(default_factory=utcnow)
    result: str
    quantitative: dict[str, float] = Field(default_factory=dict)
    outcome_type: OutcomeType = OutcomeType.PARTIAL
    outcome_evidence_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1
