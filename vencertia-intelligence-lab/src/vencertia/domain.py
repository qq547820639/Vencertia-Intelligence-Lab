from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class SourceType(str, Enum):
    REAL_PAYMENT = "real_payment"
    CONTRACT = "contract"
    OBSERVED_BEHAVIOR = "observed_behavior"
    EXPERIMENT = "experiment"
    OFFICIAL_DATA = "official_data"
    PRIMARY_RESEARCH = "primary_research"
    RELIABLE_SECONDARY = "reliable_secondary"
    EXPERT_INPUT = "expert_input"
    FOUNDER_REPORT = "founder_report"
    MODEL_INFERENCE = "model_inference"

class Verification(str, Enum):
    VERIFIED = "verified"
    ESTIMATED = "estimated"
    ASSUMED = "assumed"
    UNKNOWN = "unknown"

class Direction(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"

class DecisionStatus(str, Enum):
    GO = "go"
    CONDITIONAL_GO = "conditional_go"
    HOLD = "hold"
    PIVOT = "pivot"
    KILL = "kill"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class Belief(BaseModel):
    id: str
    statement: str
    alpha: float = Field(default=1.0, gt=0)
    beta: float = Field(default=1.0, gt=0)
    decision_weight: float = Field(default=1.0, ge=0)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def probability(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def evidence_mass(self) -> float:
        return self.alpha + self.beta - 2.0

    @property
    def uncertainty(self) -> float:
        # normalized Bernoulli variance: 1 at p=.5, 0 at p in {0,1}; shrinks with evidence mass.
        p = self.probability
        variance = 4.0 * p * (1.0-p)
        maturity = 1.0 / (1.0 + self.evidence_mass/6.0)
        return max(0.0, min(1.0, variance * (0.35 + 0.65*maturity)))

class Evidence(BaseModel):
    id: str
    belief_id: str
    claim: str
    source_type: SourceType
    verification: Verification = Verification.UNKNOWN
    direction: Direction
    strength: float = Field(ge=0, le=1)
    source_reliability: float = Field(default=0.7, ge=0, le=1)
    directness: float = Field(default=0.7, ge=0, le=1)
    independence_key: str | None = None
    observed_at: datetime = Field(default_factory=utcnow)
    source_ref: str | None = None

class EvidenceApplication(BaseModel):
    evidence_id: str
    belief_id: str
    effective_weight: float
    alpha_delta: float
    beta_delta: float
    deduplication_discount: float

class DecisionOption(BaseModel):
    id: str
    label: str
    base_utility: float = 0.0
    belief_coefficients: dict[str, float] = Field(default_factory=dict)
    irreversible_cost: float = Field(default=0.0, ge=0)
    opportunity_cost: float = Field(default=0.0, ge=0)

class DecisionRequest(BaseModel):
    id: str
    question: str
    objective: str
    options: list[DecisionOption]
    beliefs: list[Belief]
    evidence: list[Evidence] = Field(default_factory=list)
    risk_aversion: float = Field(default=0.25, ge=0, le=2)
    minimum_decision_margin: float = Field(default=0.08, ge=0)
    max_unresolved_critical_uncertainty: float = Field(default=0.45, ge=0, le=1)

    @model_validator(mode='after')
    def validate_refs(self):
        ids={b.id for b in self.beliefs}
        for e in self.evidence:
            if e.belief_id not in ids:
                raise ValueError(f"Evidence {e.id} refers to unknown belief {e.belief_id}")
        for o in self.options:
            missing=set(o.belief_coefficients)-ids
            if missing:
                raise ValueError(f"Option {o.id} refers to unknown beliefs: {sorted(missing)}")
        if len(self.options) < 2:
            raise ValueError("A decision requires at least two options")
        return self

class OptionScore(BaseModel):
    option_id: str
    expected_utility: float
    uncertainty_penalty: float
    adjusted_utility: float

class DecisionResult(BaseModel):
    decision_id: str
    status: DecisionStatus
    recommended_option_id: str | None
    confidence: float = Field(ge=0, le=1)
    decision_margin: float
    option_scores: list[OptionScore]
    critical_belief_id: str | None
    critical_uncertainty: float
    rationale: list[str]
    reversible_next_step: str | None = None

class Experiment(BaseModel):
    id: str
    name: str
    target_belief_ids: list[str]
    expected_information_gain: float = Field(ge=0)
    decision_impact: float = Field(ge=0)
    cost: float = Field(default=1.0, gt=0)
    days: float = Field(default=1.0, gt=0)
    reversibility: float = Field(default=1.0, ge=0, le=1)
    description: str
    success_signal: str
    failure_signal: str

class RankedExperiment(BaseModel):
    experiment: Experiment
    priority_score: float

class SolveRequest(BaseModel):
    decision: DecisionRequest
    experiments: list[Experiment] = Field(default_factory=list)

class SolveResult(BaseModel):
    decision: DecisionResult
    next_experiment: RankedExperiment | None = None
    evidence_applications: list[EvidenceApplication] = Field(default_factory=list)


class HistoricalDecisionCase(BaseModel):
    id: str
    t0_timestamp: datetime
    domain: str = "venture"
    decision: DecisionRequest
    experiments: list[Experiment] = Field(default_factory=list)
    t0_context: str
    future_outcome: str | None = None
    resolved_at: datetime | None = None
    reference_option_id: str | None = None
    reference_experiment_id: str | None = None
    leakage_audit_passed: bool = False
    reviewer_ids: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode='after')
    def validate_reference(self):
        ids={o.id for o in self.decision.options}
        if self.reference_option_id and self.reference_option_id not in ids and self.reference_option_id != 'NO_DECISION':
            raise ValueError('reference_option_id must be an option id or NO_DECISION')
        return self

class PredictionRecord(BaseModel):
    id: str
    target: str
    probability: float = Field(gt=0, lt=1)
    due_at: datetime
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    outcome: Literal[0,1] | None = None
    model_tag: str = "unknown"
    domain: str = "general"

class CalibrationReport(BaseModel):
    n: int
    brier_score: float | None
    expected_calibration_error: float | None
    mean_confidence: float | None
    empirical_rate: float | None
    bins: list[dict]
