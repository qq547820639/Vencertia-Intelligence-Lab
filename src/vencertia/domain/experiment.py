"""Experiment: information-acquisition actions (separate from decision options)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import ExperimentStatus, VencertiaBaseModel, utcnow


class Experiment(VencertiaBaseModel):
    id: str  # EXP_...
    name: str
    decision_id: str | None = None
    target_belief_ids: list[str] = Field(default_factory=list)
    hypothesis: str = ""
    action: str = ""
    predicted_observation: str = ""
    success_criteria: str = ""
    failure_criteria: str = ""
    ambiguity_criteria: str = ""
    expected_information_gain: float = Field(default=0.0, ge=0)
    decision_impact: float = Field(default=0.0, ge=0)
    cost: float = Field(default=1.0, gt=0)
    time: float = Field(default=1.0, gt=0)  # days
    reversibility: float = Field(default=1.0, ge=0, le=1)
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    outcome_evidence_id: str | None = None
    # v1.1 experiment-quality fields (all optional, backward compatible)
    executability: float = Field(default=1.0, ge=0, le=1)
    founder_constraints: dict = Field(default_factory=dict)
    sample_quality: float = Field(default=0.5, ge=0, le=1)
    ambiguity_clarity: float = Field(default=0.5, ge=0, le=1)
    measurement_reliability: float = Field(default=0.5, ge=0, le=1)
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    version: int = 1


class RankedExperiment(VencertiaBaseModel):
    experiment: Experiment
    priority_score: float
