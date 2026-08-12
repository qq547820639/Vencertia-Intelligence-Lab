"""BeliefEngine — Beta-Bernoulli pseudo-count updates (docs/belief-engine.md).

Beliefs are derived state: every update records update_method and the evidence
chain. Company-case evidence is gated: non-eligible case facts may only update
WORLD/MARKET priors; eligible case facts update project priors (never
pseudo-counts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    ConflictAlert,
    Direction,
    Evidence,
    EvidenceApplication,
    Scope,
    UpdateMethod,
)
from vencertia.runtime.evidence_policy import EvidencePolicy


@dataclass
class BeliefUpdateInput:
    beliefs: list[Belief]
    evidence: list[Evidence]  # already graded / authority-assigned
    update_method: UpdateMethod = UpdateMethod.BETA_BERNOULLI
    policy: EvidencePolicy | None = None
    max_pseudo_observations: float = 3.0
    conflict_weight_threshold: float = 0.3


@dataclass
class BeliefUpdateOutput:
    beliefs: list[Belief]
    applications: list[EvidenceApplication] = field(default_factory=list)
    conflicts: list[ConflictAlert] = field(default_factory=list)


class BeliefEngine:
    """Deterministic belief update (Beta-Bernoulli default; log-odds available)."""

    def __init__(self, settings: Settings | None = None, policy: EvidencePolicy | None = None) -> None:
        self.settings = settings or get_settings()
        self.policy = policy or EvidencePolicy(self.settings)

    # -- public API ----------------------------------------------------------

    def update(self, inp: BeliefUpdateInput) -> BeliefUpdateOutput:
        if inp.update_method == UpdateMethod.WEIGHTED_LOG_ODDS:
            return self._update_log_odds(inp)
        return self._update_beta_bernoulli(inp)

    def uncertainty_of(self, belief: Belief) -> float:
        """Normalized uncertainty from posterior + evidence maturity."""
        p = min(max(belief.probability, 0.0), 1.0)
        variance = 4.0 * p * (1.0 - p)
        evidence_mass = max(0.0, belief.alpha + belief.beta - 2.0)
        maturity = 1.0 / (1.0 + evidence_mass / 6.0)
        return max(0.0, min(1.0, variance * (0.35 + 0.65 * maturity)))

    def prior_of(self, belief: Belief) -> float:
        return belief.prior

    # -- Beta-Bernoulli ------------------------------------------------------

    def _update_beta_bernoulli(self, inp: BeliefUpdateInput) -> BeliefUpdateOutput:
        by_id = {b.id: b.model_copy(deep=True) for b in inp.beliefs}
        seen: dict[tuple[str, str], int] = {}
        applications: list[EvidenceApplication] = []
        support_weights: dict[str, float] = {}
        contradict_weights: dict[str, float] = {}

        for evidence in sorted(inp.evidence, key=lambda e: e.observed_at):
            grade = self.policy.grade(evidence)
            for belief in by_id.values():
                if belief.claim_id not in evidence.claim_ids:
                    continue
                app = self._apply_one(
                    belief=belief,
                    evidence=evidence,
                    grade_weight=grade.effective_weight,
                    scope_gate=grade.scope_gate,
                    seen=seen,
                    max_pseudo=inp.max_pseudo_observations,
                )
                if app is None:
                    continue
                applications.append(app)
                if app.scope_gate == "OK":
                    if evidence.supports_or_contradicts == Direction.SUPPORTS.value:
                        support_weights[belief.claim_id] = (
                            support_weights.get(belief.claim_id, 0.0) + app.effective_weight
                        )
                    elif evidence.supports_or_contradicts == Direction.CONTRADICTS.value:
                        contradict_weights[belief.claim_id] = (
                            contradict_weights.get(belief.claim_id, 0.0) + app.effective_weight
                        )

        conflicts = self._detect_conflicts(
            support_weights, contradict_weights, inp.conflict_weight_threshold
        )
        return BeliefUpdateOutput(
            beliefs=list(by_id.values()),
            applications=applications,
            conflicts=conflicts,
        )

    def _apply_one(
        self,
        belief: Belief,
        evidence: Evidence,
        grade_weight: float,
        scope_gate: str,
        seen: dict[tuple[str, str], int],
        max_pseudo: float,
    ) -> EvidenceApplication | None:
        """Apply one evidence to one belief; returns None when gated out."""
        # Company-case prior-only gate: never touch PROJECT/CUSTOMER beliefs.
        if evidence.scope == Scope.COMPANY_CASE.value or evidence.is_company_case:
            if scope_gate == "COMPANY_CASE_PRIOR_ONLY" and belief.scope in (
                Scope.PROJECT.value,
                Scope.CUSTOMER.value,
            ):
                return None
            return self._apply_company_case_prior(belief, evidence, grade_weight, scope_gate)

        # Independence/dedup discount within the same group.
        group_key = evidence.independence_group or f"__unique__:{evidence.id}"
        key = (belief.id, group_key)
        index = seen.get(key, 0)
        seen[key] = index + 1
        discount = 1.0 / (1.0 + index)

        weight = grade_weight * discount
        mass = max_pseudo * weight
        alpha_delta = beta_delta = 0.0
        direction = evidence.supports_or_contradicts
        if direction == Direction.SUPPORTS.value or direction == "SUPPORTS":
            alpha_delta = mass
        elif direction == Direction.CONTRADICTS.value or direction == "CONTRADICTS":
            beta_delta = mass
        else:  # NEUTRAL
            alpha_delta = beta_delta = 0.15 * mass

        belief.alpha += alpha_delta
        belief.beta += beta_delta
        self._refresh_belief(belief, evidence.observed_at)
        if direction == Direction.SUPPORTS.value or direction == "SUPPORTS":
            if evidence.id not in belief.supporting_evidence_ids:
                belief.supporting_evidence_ids.append(evidence.id)
        elif direction == Direction.CONTRADICTS.value or direction == "CONTRADICTS":
            if evidence.id not in belief.contradicting_evidence_ids:
                belief.contradicting_evidence_ids.append(evidence.id)

        return EvidenceApplication(
            evidence_id=evidence.id,
            belief_id=belief.id,
            effective_weight=weight,
            alpha_delta=alpha_delta,
            beta_delta=beta_delta,
            dedup_discount=discount,
            scope_gate=scope_gate,
            prior_only=False,
        )

    def _apply_company_case_prior(
        self,
        belief: Belief,
        evidence: Evidence,
        grade_weight: float,
        scope_gate: str,
    ) -> EvidenceApplication:
        """Prior-only update: shifts posterior without touching pseudo-counts."""
        transferability = evidence.transferability or 0.0
        direction = evidence.supports_or_contradicts
        prior = belief.posterior
        if direction == Direction.SUPPORTS.value or direction == "SUPPORTS":
            delta = grade_weight * (1.0 - prior)
        elif direction == Direction.CONTRADICTS.value or direction == "CONTRADICTS":
            delta = -grade_weight * prior
        else:
            delta = 0.0
        new_posterior = max(0.0, min(1.0, prior + delta))
        belief.prior = prior
        object.__setattr__(belief, "posterior", new_posterior)
        object.__setattr__(belief, "probability", new_posterior)
        belief.updated_at = evidence.observed_at or evidence.created_at
        belief.version += 1
        if direction == Direction.SUPPORTS.value or direction == "SUPPORTS":
            if evidence.id not in belief.supporting_evidence_ids:
                belief.supporting_evidence_ids.append(evidence.id)
        elif direction == Direction.CONTRADICTS.value or direction == "CONTRADICTS":
            if evidence.id not in belief.contradicting_evidence_ids:
                belief.contradicting_evidence_ids.append(evidence.id)
        return EvidenceApplication(
            evidence_id=evidence.id,
            belief_id=belief.id,
            effective_weight=grade_weight,
            alpha_delta=0.0,
            beta_delta=0.0,
            dedup_discount=1.0,
            scope_gate=scope_gate,
            prior_only=True,
        )

    def _refresh_belief(self, belief: Belief, observed_at=None) -> None:
        belief.posterior = belief.alpha / (belief.alpha + belief.beta)
        object.__setattr__(belief, "probability", belief.posterior)
        belief.uncertainty = self.uncertainty_of(belief)
        belief.confidence = 1.0 - belief.uncertainty
        belief.updated_at = observed_at or belief.updated_at
        belief.version += 1

    # -- log-odds (replaceable, [H2]) ----------------------------------------

    def _update_log_odds(self, inp: BeliefUpdateInput) -> BeliefUpdateOutput:
        """Weighted log-odds update (heuristic Bayesian-like)."""
        by_id = {b.id: b.model_copy(deep=True) for b in inp.beliefs}
        applications: list[EvidenceApplication] = []
        for evidence in sorted(inp.evidence, key=lambda e: e.observed_at):
            grade = self.policy.grade(evidence)
            for belief in by_id.values():
                if belief.claim_id not in evidence.claim_ids:
                    continue
                if evidence.scope == Scope.COMPANY_CASE.value or evidence.is_company_case:
                    if grade.scope_gate == "COMPANY_CASE_PRIOR_ONLY" and belief.scope in (
                        Scope.PROJECT.value,
                        Scope.CUSTOMER.value,
                    ):
                        continue
                odds = belief.posterior / max(1e-6, 1.0 - belief.posterior)
                sign = 1.0
                if evidence.supports_or_contradicts == Direction.CONTRADICTS.value:
                    sign = -1.0
                elif evidence.supports_or_contradicts == Direction.NEUTRAL.value:
                    sign = 0.0
                new_log_odds = __import__("math").log(odds) + sign * grade.effective_weight
                new_p = 1.0 / (1.0 + __import__("math").exp(-new_log_odds))
                belief.prior = belief.posterior
                object.__setattr__(belief, "posterior", new_p)
                object.__setattr__(belief, "probability", new_p)
                belief.uncertainty = self.uncertainty_of(belief)
                belief.confidence = 1.0 - belief.uncertainty
                belief.update_method = UpdateMethod.WEIGHTED_LOG_ODDS
                belief.updated_at = evidence.observed_at
                belief.version += 1
                applications.append(
                    EvidenceApplication(
                        evidence_id=evidence.id,
                        belief_id=belief.id,
                        effective_weight=grade.effective_weight,
                        alpha_delta=0.0,
                        beta_delta=0.0,
                        scope_gate=grade.scope_gate,
                    )
                )
        return BeliefUpdateOutput(beliefs=list(by_id.values()), applications=applications)

    # -- conflict detection ----------------------------------------------------

    def _detect_conflicts(
        self,
        support_weights: dict[str, float],
        contradict_weights: dict[str, float],
        threshold: float,
    ) -> list[ConflictAlert]:
        conflicts: list[ConflictAlert] = []
        for claim_id in set(support_weights).intersection(contradict_weights):
            sw = support_weights[claim_id]
            cw = contradict_weights[claim_id]
            if sw >= threshold and cw >= threshold:
                conflicts.append(
                    ConflictAlert(
                        claim_id=claim_id,
                        evidence_ids=[],
                        reason=(
                            "Supporting and contradicting evidence both exceed "
                            f"the conflict weight threshold ({threshold})."
                        ),
                        weight_support=sw,
                        weight_contradict=cw,
                    )
                )
        return conflicts
