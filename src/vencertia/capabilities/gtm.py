"""GtmCapability — candidate DecisionOption / experiment / action planning."""

from __future__ import annotations

from uuid import uuid4

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import Experiment
from vencertia.domain.context import ContextBundle


class GtmCapability:
    name = "gtm"

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        experiments = [
            Experiment(
                id=f"EXP_{uuid4().hex}",
                name="Outreach 20 ICPs with a paid concierge pilot offer",
                target_belief_ids=[b.id for b in context.critical_assumptions],
                hypothesis="At least 2 of 20 ICPs pay for a manual pilot.",
                action="Run 20 personalized outreach messages offering the promised outcome manually.",
                predicted_observation=">=2 paid pilots",
                success_criteria=">=2 paid pilots",
                failure_criteria="0 paid pilots",
                ambiguity_criteria="1 paid pilot",
                expected_information_gain=0.9,
                decision_impact=1.0,
                cost=1.0,
                time=3.0,
                reversibility=1.0,
            )
        ]
        return CapabilityResult(
            experiments=experiments,
            notes=["Candidate experiments only; selection by ExperimentOptimizer."],
        )
