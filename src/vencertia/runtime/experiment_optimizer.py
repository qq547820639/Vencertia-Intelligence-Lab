"""ExperimentOptimizer — ranks information-acquisition actions (ADR-003).

Decision options and experiments are strictly separated: experiments never
participate in EU scoring. When a decision is ABSTAIN, the orchestrator must
emit both the ABSTAIN result and the top-ranked experiment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from vencertia.config import Settings, get_settings
from vencertia.domain import Belief, Decision, Experiment, RankedExperiment


@dataclass
class ExperimentProposalInput:
    decision: Decision
    beliefs: list[Belief]
    critical_belief_id: Optional[str] = None
    candidates: list[Experiment] = field(default_factory=list)
    max_results: int = 5


@dataclass
class ExperimentProposalOutput:
    ranked: list[RankedExperiment]
    decision_insufficient: bool
    reason: str


class ExperimentOptimizer:
    """Deterministic experiment scoring (docs/experiment-optimizer.md)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

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
            score = (
                experiment.expected_information_gain
                * experiment.decision_impact
                * uncertainty
                * reversibility_bonus
                * critical_boost
            ) / denominator
            ranked.append(
                RankedExperiment(experiment=experiment, priority_score=round(score, 6))
            )
        ranked.sort(key=lambda r: r.priority_score, reverse=True)
        return ranked

    def propose(self, inp: ExperimentProposalInput) -> ExperimentProposalOutput:
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
