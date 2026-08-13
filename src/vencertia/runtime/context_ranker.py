"""Decision-relevant context construction and ranking (ADR-010).

Combines 15 context classes and ranks evidence with 10 deterministic
dimensions. The baseline is fully deterministic/lexical; a SemanticRanker
adapter can be injected later (vector store per ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    CriticalUncertainty,
    Decision,
    Evidence,
    FounderProfile,
    Outcome,
    Project,
    Scope,
    utcnow,
)
from vencertia.domain.context import ContextBundleV11
from vencertia.repositories.base import Repository
from vencertia.runtime.evidence_policy import AUTHORITY_TABLE


@dataclass
class SemanticRanker(Protocol):
    """Vector ranker adapter (v1.1 not implemented; deterministic baseline)."""

    def rank(self, query: str, candidates: list[str]) -> list[float]: ...


class ContextRanker:
    """Deterministic evidence ranking over 10 configurable dimensions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def score_evidence(
        self,
        evidence: Evidence,
        decision: Decision | None,
        beliefs: list[Belief],
        claim_by_belief: dict[str, str] | None = None,
    ) -> float:
        weights = self.settings.context_rank_weights
        scope_match = self._scope_match(evidence)
        decision_relevance = self._decision_relevance(evidence, decision, claim_by_belief)
        belief_dependency = self._belief_dependency(evidence, beliefs)
        authority = self._authority(evidence)
        evidence_strength = (evidence.strength or 0.0) * (evidence.relevance or 0.0)
        temporal_validity = self._temporal_validity(evidence)
        recency = self._recency(evidence)
        conflict = 0.0 if evidence.conflict_status in (None, "NO_CONFLICT") else 0.5
        semantic = self._semantic(evidence, decision)
        information_value = min(1.0, (1.0 - evidence.directness) + (evidence.reliability or 0.0))

        score = (
            weights.get("scope_match", 0.15) * scope_match
            + weights.get("decision_relevance", 0.20) * decision_relevance
            + weights.get("belief_dependency", 0.10) * belief_dependency
            + weights.get("authority", 0.15) * authority
            + weights.get("evidence_strength", 0.10) * evidence_strength
            + weights.get("temporal_validity", 0.05) * temporal_validity
            + weights.get("recency", 0.10) * recency
            + weights.get("conflict", 0.05) * conflict
            + weights.get("semantic", 0.05) * semantic
            + weights.get("information_value", 0.05) * information_value
        )
        return round(score, 6)

    @staticmethod
    def _scope_match(evidence: Evidence) -> float:
        scope = evidence.scope.value if hasattr(evidence.scope, "value") else str(evidence.scope)
        if scope == Scope.PROJECT.value:
            return 1.0
        if scope in (Scope.CUSTOMER.value, Scope.MARKET.value):
            return 0.7
        if scope == Scope.WORLD.value:
            return 0.5
        if scope == Scope.COMPANY_CASE.value:
            return 0.3
        return 0.4

    @staticmethod
    def _decision_relevance(
        evidence: Evidence,
        decision: Decision | None,
        claim_by_belief: dict[str, str] | None = None,
    ) -> float:
        """P0-2: relevance of evidence to a decision via REAL belief→claim mapping.

        ID-namespace discipline (ADR-014): ``Evidence.claim_ids`` are CLM_* and
        ``Decision.relevant_belief_ids`` are BLF_*. Cross-namespace comparison is
        FORBIDDEN — we resolve beliefs to claims through ``claim_by_belief``
        (built from the repository's canonical Belief records) and intersect
        with the evidence's claim ids. No string guessing (e.g. ``f"CLM_{r}"``).

        Without a mapping (pure legacy callers) the score degrades to a neutral
        0.5 — never a fabricated match.
        """
        if decision is None:
            return 0.5
        claim_ids = {c for c in (evidence.claim_ids or [])}
        if not claim_ids:
            return 0.3
        if claim_by_belief:
            relevant_claim_ids = {
                claim_by_belief[bid]
                for bid in (decision.relevant_belief_ids or [])
                if bid in claim_by_belief
            }
            if relevant_claim_ids and claim_ids.intersection(relevant_claim_ids):
                return 1.0
            return 0.4
        # No mapping available (legacy caller): neutral, never a string guess.
        return 0.5

    @staticmethod
    def _belief_dependency(evidence: Evidence, beliefs: list[Belief]) -> float:
        if not beliefs or not evidence.claim_ids:
            return 0.0
        claim_to_belief = {b.claim_id: b for b in beliefs}
        hits = sum(1 for cid in evidence.claim_ids if cid in claim_to_belief)
        return min(1.0, hits / max(1, len(evidence.claim_ids)))

    @staticmethod
    def _authority(evidence: Evidence) -> float:
        key = evidence.authority_level.value if hasattr(evidence.authority_level, "value") else str(evidence.authority_level)
        return AUTHORITY_TABLE.get(key, 0.1)

    @staticmethod
    def _temporal_validity(evidence: Evidence, now: datetime | None = None) -> float:
        now = now or utcnow()
        if evidence.valid_until is not None and now > evidence.valid_until:
            return 0.0
        if evidence.valid_from is not None and now < evidence.valid_from:
            return 0.0
        if evidence.freshness_score is not None:
            return float(evidence.freshness_score)
        return 0.8

    @staticmethod
    def _recency(evidence: Evidence, now: datetime | None = None) -> float:
        now = now or utcnow()
        observed = evidence.observed_at or evidence.created_at
        age_days = max(0.0, (now - observed).total_seconds() / 86400.0)
        return round(max(0.0, min(1.0, 1.0 - age_days / 365.0)), 6)

    def _semantic(self, evidence: Evidence, decision: Decision | None) -> float:
        # Baseline: lexical overlap between the evidence source and the decision
        # question. A SemanticRanker adapter would replace this (v1.1).
        if decision is None or not decision.decision_question:
            return 0.0
        from vencertia.runtime.claim_binding import lexical_overlap

        return lexical_overlap(evidence.source, decision.decision_question)


class DecisionRelevantContextBuilder:
    """Builds a 15-class ContextBundleV11 for a decision (read-only)."""

    def __init__(
        self,
        repo: Repository,
        ranker: ContextRanker | None = None,
        semantic: SemanticRanker | None = None,
    ) -> None:
        self.repo = repo
        self.ranker = ranker or ContextRanker()
        self.semantic = semantic

    def build_for_decision(
        self,
        project_id: str,
        decision: Decision | None = None,
        user_id: str | None = None,
        limit: int = 15,
    ) -> ContextBundleV11:
        project = self.repo.get_project(project_id)
        owner = user_id or (project.user_id if project else "unknown")
        beliefs = self.repo.get_beliefs(project_id)
        # P0-3: read boundary — only project-owned + explicitly shared evidence.
        evidence = self.repo.list_evidence(project_id=project_id)
        decisions = sorted(
            self.repo.list_decisions(project_id), key=lambda d: d.updated_at, reverse=True
        )
        experiments = sorted(
            self.repo.list_experiments(project_id), key=lambda e: e.created_at, reverse=True
        )
        claims = self.repo.list_claims(project_id)
        objectives = (
            [self.repo.get_objective(decisions[0].objective_id)] if decisions else []
        )
        objectives = [o for o in objectives if o is not None]
        # P0-4: recent_outcomes via the public Repository API. Outcomes are
        # keyed OUT_* and reference actions by action_id (ACT_*); never assume
        # Outcome.id == Action.id and never touch private ``repo._list``.
        outcomes: list[Outcome] = []
        for d in decisions:
            for action in self.repo.list_actions(decision_id=d.id):
                outcomes.extend(self.repo.list_outcomes(action_id=action.id))
        outcomes.sort(key=lambda o: o.observed_at, reverse=True)
        founder_profile: FounderProfile | None = None
        if project is not None:
            founder_profile = self.repo.get_founder_profile(project.user_id)
        company_cases = self.repo.list_company_cases()
        financial_snapshots = self.repo.list_financial_snapshots(project_id)
        critical_uncertainties: list[CriticalUncertainty] = []
        latest = decisions[0] if decisions else decision
        if latest is not None and beliefs:
            from vencertia.runtime.uncertainty_engine import UncertaintyEngine

            critical_uncertainties = UncertaintyEngine().rank(latest, beliefs)

        # P0-2: real belief→claim mapping for decision relevance (no guessing).
        claim_by_belief = {b.id: b.claim_id for b in beliefs}
        evidence_sorted = sorted(
            evidence,
            key=lambda e: self.ranker.score_evidence(
                e, latest or decision, beliefs, claim_by_belief=claim_by_belief
            ),
            reverse=True,
        )
        strong_evidence = [
            e
            for e in evidence_sorted
            if self.ranker.score_evidence(
                e, latest or decision, beliefs, claim_by_belief=claim_by_belief
            )
            >= 0.5
        ][:limit]
        contradictory_evidence = [
            e
            for e in evidence_sorted
            if str(getattr(e, "supports_or_contradicts", "NEUTRAL")) == "CONTRADICTS"
        ][:limit]
        open_experiments = [e for e in experiments if str(e.status) in ("PROPOSED", "RUNNING")]

        return ContextBundleV11(
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
            latest_decisions=decisions[:limit],
            latest_experiments=experiments[:limit],
            objectives=objectives,
            claims=claims,
            strong_evidence=strong_evidence,
            contradictory_evidence=contradictory_evidence,
            recent_outcomes=outcomes,
            open_experiments=open_experiments,
            previous_decisions=decisions[:limit],
            company_cases=company_cases,
            financial_snapshots=financial_snapshots,
            constraints=self._constraints(project),
            critical_uncertainties=critical_uncertainties,
        )

    @staticmethod
    def _constraints(project: Project | None) -> list[str]:
        if project is None:
            return []
        raw = getattr(project, "constraints", None)
        if isinstance(raw, list):
            return [str(c) for c in raw]
        return []
