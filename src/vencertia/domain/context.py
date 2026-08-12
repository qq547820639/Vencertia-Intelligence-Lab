"""ContextBundle DTOs (P2-15) — domain-layer capability contract.

Context is a DTO (ADR-001): it is NEVER persisted. Moving the bundle types
into the domain layer fixes the layer cycle ``capabilities → runtime.context
→ runtime → capabilities``: now capabilities depend on domain only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from vencertia.domain import (
    Belief,
    Claim,
    CompanyCase,
    ConflictAlert,
    CriticalUncertainty,
    Decision,
    Evidence,
    Experiment,
    FinancialSnapshot,
    FounderProfile,
    Objective,
    Outcome,
    Project,
    utcnow,
)


@dataclass
class ContextBundle:
    """Read projection of REALITY state for capability consumption."""

    user_id: str
    project: Project | None = None
    project_snapshot: dict = field(default_factory=dict)
    founder_profile: FounderProfile | None = None
    critical_assumptions: list[Belief] = field(default_factory=list)
    top_evidence: list[Evidence] = field(default_factory=list)
    latest_decisions: list[Decision] = field(default_factory=list)
    latest_experiments: list[Experiment] = field(default_factory=list)
    conflict_alerts: list[ConflictAlert] = field(default_factory=list)
    as_of: datetime = field(default_factory=utcnow)


@dataclass
class ContextBundleV11(ContextBundle):
    """Extended context projection (all new fields optional, backward compatible)."""

    objectives: list[Objective] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    strong_evidence: list[Evidence] = field(default_factory=list)
    contradictory_evidence: list[Evidence] = field(default_factory=list)
    recent_outcomes: list[Outcome] = field(default_factory=list)
    open_experiments: list[Experiment] = field(default_factory=list)
    previous_decisions: list[Decision] = field(default_factory=list)
    company_cases: list[CompanyCase] = field(default_factory=list)
    financial_snapshots: list[FinancialSnapshot] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    critical_uncertainties: list[CriticalUncertainty] = field(default_factory=list)
    conflict_alerts: list = field(default_factory=list)


__all__ = ["ContextBundle", "ContextBundleV11"]
