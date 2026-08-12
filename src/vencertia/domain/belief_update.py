"""Belief update records — every belief mutation is traceable (v1.1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class BeliefUpdateRecord(VencertiaBaseModel):
    """One immutable record of a single belief update batch.

    Captures old/new probability and uncertainty plus every discount that
    shaped the effective weight (correlation / scope / freshness), so the
    Belief Delta Quality metric has a trustworthy data source.
    """

    id: str  # BUR_...
    belief_id: str
    claim_id: str
    old_probability: float = Field(ge=0, le=1)
    old_uncertainty: float = Field(ge=0, le=1)
    evidence_used: list[str] = Field(default_factory=list)
    authority: str = ""
    verification: str = ""
    correlation_discount: float = Field(default=1.0, ge=0, le=1)
    scope_discount: float = Field(default=1.0, ge=0, le=1)
    freshness_discount: float = Field(default=1.0, ge=0, le=1)
    effective_weight: float = 0.0
    new_probability: float = Field(ge=0, le=1)
    new_uncertainty: float = Field(ge=0, le=1)
    conflict_uncertainty_raise: float = Field(default=0.0, ge=0, le=1)
    update_method: str = "BETA_BERNOULLI"
    policy_version: str = "1.1"
    posterior_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1
