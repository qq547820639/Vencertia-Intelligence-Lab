"""Decision-relevant context construction and ranking (ADR-010).

Combines 15 context classes and ranks evidence with 10 deterministic
dimensions. The baseline is fully deterministic/lexical; a SemanticRanker
adapter can be injected later (vector store per ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Claim,
    CompanyCase,
    CriticalUncertainty,
    Decision,
    Evidence,
    Experiment,
    FinancialSnapshot,
    FounderProfile,
    Objective,
    Outcome,
    Project,
    Scope,
    utcnow,
)
from vencertia.repositories.base import Repository
from vencertia.runtime.context import ContextBundle


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
    ) -> float:
        weights = self.settings.context_rank_weights
        scope_match = self._scope_match(evidence)
        decision_relevance = self._decision_relevance(evidence, decision)
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
    def _decision_relevance(evidence: Evidence, decision: Decision | None) -> float:
        if decision is None:
            return 0.5
        claim_ids = {c for c in (evidence.claim_ids or [])}
        relevant = {b for b in (decision.relevant_belief_ids or [])}
        if not claim_ids:
            return 0.3
        # Heuristic: evidence with claims touching relevant beliefs scores high.
        if relevant and claim_ids.intersection({f"CLM_{r}" for r in relevant}):
            return 1.0
        if relevant and claim_ids.intersection(relevant):
            return 0.9
        return 0.4

    @staticmethod
    def _belief_dependency(evidence: Evidence, beliefs: list[Belief]) -> float:
        if not beliefs or not evidence.claim_ids:
            return 0.0
        claim_to_belief = {b.claim_id: b for b in beliefs}
        hits = sum(1 for cid in evidence.claim_ids if cid in claim_to_belief)
        return min(1.0, hits / max(1, len(evidence.claim_ids)))

    @staticmethod
    def _authority(evidence: Evidence) -> float:
        table = {
            "PROJECT_REALITY": 1.0,
            "PROJECT_DIRECT_BEHAVIOR": 0.95,
            "PROJECT_EXPERIMENT_RESULT": 0.9,
            "CUSTOMER_COMMITMENT_OR_PAYMENT": 0.88,
            "ELIGIBLE_EXTERNAL_CASE_FACT": 0.75,
            "REVIEWED_EXTERNAL_RESEARCH": 0.65,
            "FOUNDER_STATEMENT": 0.45,
            "LLM_INFERENCE": 0.2,
            "MODEL_PRIOR": 0.1,
        }
        key = evidence.authority_level.value if hasattr(evidence.authority_level, "value") else str(evidence.authority_level)
        return table.get(key, 0.1)

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
        evidence = self.repo.list_evidence()
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
        outcomes = []
        actions = []
        for d in decisions:
            actions.extend(
                [a for a in self.repo._list("action") if a.decision_id == d.id] if hasattr(self.repo, "_list") else []
            )
        for action in actions:
            outcome = self.repo.get_outcome(action.id) if hasattr(self.repo, "get_outcome") else None
            if outcome is None:
                continue
            # Outcomes are keyed by action_id; save_outcome uses outcome.id as key.
            for row in (self.repo._list("outcome") if hasattr(self.repo, "_list") else []):
                if row.action_id == action.id:
                    outcomes.append(row)
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

        evidence_sorted = sorted(
            evidence,
            key=lambda e: self.ranker.score_evidence(e, latest or decision, beliefs),
            reverse=True,
        )
        strong_evidence = [e for e in evidence_sorted if self.ranker.score_evidence(e, latest or decision, beliefs) >= 0.5][:limit]
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
