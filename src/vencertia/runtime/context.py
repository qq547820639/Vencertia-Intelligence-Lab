"""ContextBuilder — read-only projection consumed by capabilities (ADR-001).

Context is a DTO; it is never persisted. Capabilities receive ContextBundle and
return candidates only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from vencertia.domain import (
    Belief,
    ConflictAlert,
    Decision,
    Evidence,
    Experiment,
    FounderProfile,
    Project,
    utcnow,
)
from vencertia.repositories.base import Repository


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


class ContextBuilder:
    """Builds ContextBundle projections from the repository (read-only)."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def build(
        self,
        project_id: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> ContextBundle:
        project = self.repo.get_project(project_id)
        owner = user_id or (project.user_id if project else "unknown")
        beliefs = self.repo.get_beliefs(project_id)
        evidence = self.repo.list_evidence()
        decisions = self.repo.list_decisions(project_id)
        experiments = self.repo.list_experiments(project_id)

        # Sort evidence by authority weight then recency (approximation).
        def evidence_key(e: Evidence) -> tuple[float, str]:
            authority_weight = {
                "PROJECT_REALITY": 1.0,
                "PROJECT_DIRECT_BEHAVIOR": 0.95,
                "PROJECT_EXPERIMENT_RESULT": 0.9,
                "CUSTOMER_COMMITMENT_OR_PAYMENT": 0.88,
                "ELIGIBLE_EXTERNAL_CASE_FACT": 0.75,
                "REVIEWED_EXTERNAL_RESEARCH": 0.65,
                "FOUNDER_STATEMENT": 0.45,
                "LLM_INFERENCE": 0.2,
                "MODEL_PRIOR": 0.1,
            }.get(e.authority_level, 0.0)
            return (authority_weight, e.observed_at.isoformat())

        evidence_sorted = sorted(evidence, key=evidence_key, reverse=True)
        decisions_sorted = sorted(decisions, key=lambda d: d.updated_at, reverse=True)
        experiments_sorted = sorted(experiments, key=lambda e: e.created_at, reverse=True)

        founder_profile = None
        if project is not None:
            founder_profile = self.repo.get_founder_profile(project.user_id)

        return ContextBundle(
            user_id=owner,
            project=project,
            project_snapshot={
                "project_id": project.id if project else project_id,
                "name": project.name if project else "",
                "status": project.status if project else "",
                "stage": project.stage if project else "",
                "is_primary": project.is_primary if project else False,
                "beliefs": [b.id for b in beliefs],
                "decisions": [d.id for d in decisions],
                "evidence_count": len(evidence),
            },
            founder_profile=founder_profile,
            critical_assumptions=beliefs[:limit],
            top_evidence=evidence_sorted[:limit],
            latest_decisions=decisions_sorted[:limit],
            latest_experiments=experiments_sorted[:limit],
            conflict_alerts=[],
        )
