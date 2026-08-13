"""ContextBuilder — read-only projection consumed by capabilities (ADR-001).

Context is a DTO; it is never persisted. Capabilities receive ContextBundle and
return candidates only.

v1.1.2 (P2-15): the ContextBundle DTOs live in :mod:`vencertia.domain.context`
so capabilities depend on domain (no layer cycle). This module keeps the
ContextBuilder and re-exports the DTOs for backward compatibility.
"""

from __future__ import annotations

from vencertia.domain import Evidence
from vencertia.domain.context import ContextBundle, ContextBundleV11  # noqa: F401  (re-export)
from vencertia.repositories.base import Repository
from vencertia.runtime.evidence_policy import AUTHORITY_TABLE


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
        # P0-3: read boundary — only project-owned + explicitly shared evidence.
        evidence = self.repo.list_evidence(project_id=project_id)
        decisions = self.repo.list_decisions(project_id)
        experiments = self.repo.list_experiments(project_id)

        # Sort evidence by authority weight then recency (approximation).
        def evidence_key(e: Evidence) -> tuple[float, str]:
            authority_weight = AUTHORITY_TABLE.get(e.authority_level, 0.0)
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
