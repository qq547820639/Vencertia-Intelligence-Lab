"""Belief: derived state quantifying a claim (Beta-Bernoulli by default)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from vencertia.domain.base import Scope, UpdateMethod, VencertiaBaseModel, utcnow


class EvidenceApplication(VencertiaBaseModel):
    """Trace of one evidence application onto one belief."""

    evidence_id: str
    belief_id: str
    effective_weight: float
    alpha_delta: float = 0.0
    beta_delta: float = 0.0
    dedup_discount: float = Field(default=1.0, ge=0, le=1)
    scope_gate: str = "OK"  # OK | COMPANY_CASE_PRIOR_ONLY | REJECTED
    prior_only: bool = False  # True for company-case prior updates (no pseudo-count)


class ConflictAlert(VencertiaBaseModel):
    """Explicit conflict between supporting and contradicting evidence."""

    claim_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    weight_support: float = 0.0
    weight_contradict: float = 0.0


class Belief(VencertiaBaseModel):
    """Probabilistic projection of a claim.

    ``probability`` is kept in sync with ``posterior`` (output alias).
    """

    id: str  # BLF_...
    claim_id: str
    statement: str
    scope: Scope = Scope.PROJECT
    project_id: str | None = None
    prior: float = Field(default=0.5, ge=0, le=1)
    posterior: float = Field(default=0.5, ge=0, le=1)
    probability: float = Field(default=0.5, ge=0, le=1)
    uncertainty: float = Field(default=1.0, ge=0, le=1)
    confidence: float = Field(default=0.0, ge=0, le=1)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    alpha: float = Field(default=1.0, gt=0)
    beta: float = Field(default=1.0, gt=0)
    decision_weight: float = Field(default=1.0, ge=0)
    update_method: UpdateMethod = UpdateMethod.BETA_BERNOULLI
    calibration_group: str = "default"
    decision_relevant: bool = False
    # v1.1 versioning fields (all optional, backward compatible)
    posterior_version: int = 1  # incremented on every belief update
    previous_snapshot: dict | None = None  # {probability, uncertainty, alpha, beta}
    last_evidence_batch_id: str | None = None
    policy_version: str = "1.0"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1

    @model_validator(mode="after")
    def _sync_probability(self) -> Belief:
        # object.__setattr__ bypasses validate_assignment to avoid recursion.
        object.__setattr__(self, "probability", self.posterior)
        object.__setattr__(self, "confidence", max(0.0, min(1.0, 1.0 - self.uncertainty)))
        return self

    @property
    def evidence_mass(self) -> float:
        """Total pseudo-observation mass (alpha+beta−2)."""
        return self.alpha + self.beta - 2.0
