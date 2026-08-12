"""Founder domain: profile, time-varying state, opportunity portfolio."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class FounderProfile(VencertiaBaseModel):
    user_id: str
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    domain_expertise: list[str] = Field(default_factory=list)
    sales_ability: float = Field(default=0.0, ge=0, le=1)
    network: float = Field(default=0.0, ge=0, le=1)
    risk_tolerance: float = Field(default=0.5, ge=0, le=1)
    capital_access: float = Field(default=0.0, ge=0, le=1)
    motivation: float = Field(default=0.5, ge=0, le=1)
    execution_reliability: float = Field(default=0.5, ge=0, le=1)
    constraints: list[str] = Field(default_factory=list)
    red_lines: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1

    @property
    def id(self) -> str:
        """Alias so the generic repository can address this entity."""
        return self.user_id


class FounderState(VencertiaBaseModel):
    """Time-varying state; input to decision goals and action strategy."""

    user_id: str
    as_of: datetime = Field(default_factory=utcnow)
    runway_months: float | None = None
    time_available: float | None = None  # hours per week
    energy: float = Field(default=0.5, ge=0, le=1)
    skills: list[str] = Field(default_factory=list)
    network: float = Field(default=0.0, ge=0, le=1)
    domain_expertise: float = Field(default=0.0, ge=0, le=1)
    sales_ability: float = Field(default=0.0, ge=0, le=1)
    risk_tolerance: float = Field(default=0.5, ge=0, le=1)
    capital_access: float = Field(default=0.0, ge=0, le=1)
    motivation: float = Field(default=0.5, ge=0, le=1)
    execution_reliability: float = Field(default=0.5, ge=0, le=1)
    source_evidence_ids: list[str] = Field(default_factory=list)


class Opportunity(VencertiaBaseModel):
    """Member of the Founder Opportunity Portfolio."""

    project_id: str
    name: str
    expected_value: float = 0.0
    option_value: float = 0.0
    opportunity_cost: float = 0.0
    priority: int = Field(default=0, ge=0, le=10)
    as_of: datetime = Field(default_factory=utcnow)


class FounderOpportunityPortfolio(VencertiaBaseModel):
    user_id: str
    opportunities: list[Opportunity] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1

    @property
    def id(self) -> str:
        """Alias so the generic repository can address this entity."""
        return self.user_id
