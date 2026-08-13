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
from vencertia.domain.model_parameter import ModelParameter
from vencertia.domain.stakes import StakesClass, StakesProfile
from vencertia.domain.utility import UtilityComponent


class DecisionOption(VencertiaBaseModel):
    """A resource-commitment option (NOT an information-acquisition action)."""

    id: str
    label: str
    description: str = ""
    kind: DecisionType | None = None  # GO/CONDITIONAL_GO/HOLD/PIVOT/KILL/SELECT_OPTION
    # V-7: presentation-layer option kind (GO/WAIT/STAGE/TEST/HOLD/PIVOT/KILL).
    option_kind: str | None = None
    base_utility: float = 0.0
    belief_coefficients: dict[str, float] = Field(default_factory=dict)
    # V-1: provenance-annotated coefficients (optional, additive layer).
    belief_parameters: dict[str, ModelParameter] | None = None
    # V-5: non-linear utility components (None -> original linear path).
    utility_components: list[UtilityComponent] | None = None
    irreversible_cost: float = Field(default=0.0, ge=0)
    opportunity_cost: float = Field(default=0.0, ge=0)
    resource_requirements: dict[str, float] = Field(default_factory=dict)

    @property
    def effective_belief_coefficients(self) -> dict[str, float]:
        """Effective coefficient map: ``belief_coefficients`` base, overridden by
        ``belief_parameters`` (parameters take precedence on key collision)."""
        coefficients = dict(self.belief_coefficients)
        if self.belief_parameters:
            for belief_id, parameter in self.belief_parameters.items():
                coefficients[belief_id] = parameter.value
        return coefficients


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
    # V-4: stakes classification (optional; MEDIUM reproduces v1.1.2 global band).
    stakes: StakesProfile | None = None
    stakes_class: StakesClass = StakesClass.MEDIUM
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
    # V-4: adaptive ABSTAIN (default MEDIUM == v1.1.2 global thresholds).
    stakes_class: StakesClass = StakesClass.MEDIUM
    abstain_exit_condition: str | None = None
