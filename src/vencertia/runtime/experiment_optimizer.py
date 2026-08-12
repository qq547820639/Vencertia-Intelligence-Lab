"""ExperimentOptimizer — ranks information-acquisition actions (ADR-003).

Decision options and experiments are strictly separated: experiments never
participate in EU scoring. When a decision is ABSTAIN, the orchestrator must
emit both the ABSTAIN result and the top-ranked experiment.

v1.1 hardening (ADR-012): every experiment must pass deterministic validation —
success/failure/ambiguity criteria are mandatory and vague actions ("do some
more interviews") are rejected. Ranking multiplies by executability ×
measurement_reliability and penalizes low sample quality / ambiguity clarity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import Field

from vencertia.config import Settings, get_settings
from vencertia.domain import Belief, Decision, Experiment, RankedExperiment, VencertiaBaseModel

VAGUE_ACTION_PATTERN = re.compile(r"(interview|talk|chat|reach out|ask|more research|further study)", re.IGNORECASE)


class ExperimentValidationResult(VencertiaBaseModel):
    valid: bool
    reasons: list[str] = Field(default_factory=list)


@dataclass
class ExperimentProposalInput:
    decision: Decision
    beliefs: list[Belief]
    critical_belief_id: str | None = None
    candidates: list[Experiment] = field(default_factory=list)
    max_results: int = 5


@dataclass
class ExperimentProposalOutput:
    ranked: list[RankedExperiment]
    decision_insufficient: bool
    reason: str


def validate_experiment(experiment: Experiment) -> ExperimentValidationResult:
    """Criteria enforcement: success/failure/ambiguity must be non-empty and
    the action must not be vague."""
    reasons: list[str] = []
    if not (experiment.success_criteria or "").strip():
        reasons.append("success_criteria is required")
    if not (experiment.failure_criteria or "").strip():
        reasons.append("failure_criteria is required")
    if not (experiment.ambiguity_criteria or "").strip():
        reasons.append("ambiguity_criteria is required")
    action = (experiment.action or "").strip()
    if len(action) < 12:
        reasons.append("action is too vague (must be a concrete executable action)")
    if VAGUE_ACTION_PATTERN.search(action) and ("more" in action.lower() or "再" in action):
        reasons.append("action is vague ('do more interviews'-style actions are rejected)")
    return ExperimentValidationResult(valid=not reasons, reasons=reasons)


class ExperimentOptimizer:
    """Deterministic experiment scoring (docs/experiment-optimizer.md)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def validate(self, experiment: Experiment) -> ExperimentValidationResult:
        return validate_experiment(experiment)

    def rank(
        self,
        experiments: list[Experiment],
        beliefs: list[Belief],
        critical_belief_id: str | None = None,
    ) -> list[RankedExperiment]:
        bm = {b.id: b for b in beliefs}
        ranked: list[RankedExperiment] = []
        for experiment in experiments:
            target_uncertainty = sum(
                bm[bid].uncertainty * bm[bid].decision_weight
                for bid in experiment.target_belief_ids
                if bid in bm
            )
            uncertainty = max(0.05, target_uncertainty)
            reversibility_bonus = 0.5 + 0.5 * experiment.reversibility
            critical_boost = (
                2.0
                if critical_belief_id and critical_belief_id in experiment.target_belief_ids
                else 1.0
            )
            time_penalty = 1.0 + 0.15 * max(0.0, experiment.time - 1.0)
            denominator = experiment.cost * time_penalty
            base_score = (
                experiment.expected_information_gain
                * experiment.decision_impact
                * uncertainty
                * reversibility_bonus
                * critical_boost
            ) / denominator
            # v1.1 quality factors: executability × measurement_reliability,
            # with multiplicative penalties for weak sample / ambiguous criteria.
            quality_multiplier = (
                float(experiment.executability) * float(experiment.measurement_reliability)
            )
            sample_factor = 0.5 + 0.5 * float(experiment.sample_quality)
            ambiguity_factor = 0.5 + 0.5 * float(experiment.ambiguity_clarity)
            score = base_score * quality_multiplier * sample_factor * ambiguity_factor
            ranked.append(
                RankedExperiment(experiment=experiment, priority_score=round(score, 6))
            )
        ranked.sort(key=lambda r: r.priority_score, reverse=True)
        return ranked

    def propose(self, inp: ExperimentProposalInput) -> ExperimentProposalOutput:
        # NOTE: v1.0 behavior keeps ALL candidates rankable here. Criteria
        # enforcement (v1.1/ADR-012) is applied by the orchestrator/API before
        # state mutation: invalid experiments (vague action / missing criteria)
        # are rejected there via validate_experiment().
        ranked = self.rank(
            inp.candidates, inp.beliefs, critical_belief_id=inp.critical_belief_id
        )
        truncated = ranked[: max(1, inp.max_results)]
        return ExperimentProposalOutput(
            ranked=truncated,
            decision_insufficient=True,
            reason=(
                "Decision not converged: INSUFFICIENT_EVIDENCE. "
                "Run the top-ranked experiment before committing resources."
            ),
        )
