"""Decision family: options, decision, option scores, decision result."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import (
    ConvergenceStatus,
    DecisionType,
    VencertiaBaseModel,
    utcnow,
)


class DecisionOption(VencertiaBaseModel):
    """A resource-commitment option (NOT an information-acquisition action)."""

    id: str
    label: str
    description: str = ""
    kind: DecisionType | None = None  # GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION
    base_utility: float = 0.0
    belief_coefficients: dict[str, float] = Field(default_factory=dict)
    irreversible_cost: float = Field(default=0.0, ge=0)
    opportunity_cost: float = Field(default=0.0, ge=0)
    resource_requirements: dict[str, float] = Field(default_factory=dict)


class Decision(VencertiaBaseModel):
    id: str  # DEC_...
    decision_question: str
    objective_id: str
    project_id: str
    options: list[DecisionOption] = Field(min_length=1)
    decision_type: DecisionType | None = None
    horizon: str = "short"  # short | medium | long
    reversible: bool = True
    estimated_cost: float = 0.0
    relevant_belief_ids: list[str] = Field(default_factory=list)
    critical_uncertainty_ids: list[str] = Field(default_factory=list)
    current_recommendation: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    convergence_status: ConvergenceStatus = ConvergenceStatus.NOT_CONVERGED
    status: str = "DRAFT"  # DRAFT | EVALUATED | EXECUTED
    snapshot_hash: str | None = None
    rationale: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1


class OptionScore(VencertiaBaseModel):
    option_id: str
    expected_utility: float
    uncertainty_penalty: float
    adjusted_utility: float


class DecisionResult(VencertiaBaseModel):
    """Output of the DecisionEngine (also aliased DecisionEngineOutput)."""

    decision_id: str
    status: DecisionType
    recommended_option_id: str | None
    confidence: float = Field(ge=0, le=1)
    decision_margin: float
    option_scores: list[OptionScore] = Field(default_factory=list)
    critical_belief_id: str | None = None
    critical_uncertainty: float = 0.0
    convergence_status: ConvergenceStatus = ConvergenceStatus.NOT_CONVERGED
    rationale: list[str] = Field(default_factory=list)
    reversible_next_step: str | None = None
