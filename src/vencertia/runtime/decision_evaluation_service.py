"""DecisionEvaluationService — convergence + decision engine + trace + sensitivity
(P2-16). Extracted from SolveOrchestrator; behavior identical to v1.1.1.
"""

from __future__ import annotations

from typing import Any

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Decision,
    DecisionResult,
    DecisionSensitivity,
    DecisionTrace,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.repositories.base import Repository
from vencertia.runtime.decision_engine import DecisionEngineInput


class DecisionEvaluationService:
    """Runs the post-research evaluation pipeline for a decision."""

    def __init__(
        self,
        repo: Repository,
        engines,
        settings: Settings | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.repo = repo
        self.engines = engines
        self.settings = settings or get_settings()
        self.bus = bus

    def evaluate(
        self,
        decision: Decision,
        beliefs: list[Belief],
        risk_aversion: float | None = None,
        minimum_margin: float | None = None,
        max_critical_uncertainty: float | None = None,
        experiments: list | None = None,
        research_stop_status: str | None = None,
    ) -> tuple[DecisionResult, Any, DecisionTrace, DecisionSensitivity | None]:
        """Convergence check → decision evaluate → trace → sensitivity.

        Returns ``(decision_result, convergence, decision_trace, sensitivity)``.
        """
        criticals = self.engines.uncertainty_engine.rank(decision, beliefs)
        experiments = experiments or self.repo.list_experiments(decision.project_id)
        pre_convergence = self.engines.convergence_engine.check(
            decision,
            beliefs,
            criticals,
            experiments=experiments,
            research_stop_status=research_stop_status,
        )
        ra = risk_aversion if risk_aversion is not None else self.settings.risk_aversion
        mm = minimum_margin if minimum_margin is not None else self.settings.minimum_margin
        mcu = (
            max_critical_uncertainty
            if max_critical_uncertainty is not None
            else self.settings.max_critical_uncertainty
        )
        decision_result = self.engines.decision_engine.evaluate(
            DecisionEngineInput(
                decision=decision,
                beliefs=beliefs,
                risk_aversion=ra,
                minimum_margin=mm,
                max_critical_uncertainty=mcu,
                convergence_status=pre_convergence.status,
                convergence_reason=pre_convergence.reason,
            )
        )
        if decision_result.status == "ABSTAIN":
            convergence = pre_convergence
        else:
            convergence = self.engines.convergence_engine.check(
                decision,
                beliefs,
                criticals,
                experiments=experiments,
                decision_status=decision_result.status,
                research_stop_status=research_stop_status,
            )

        decision_trace = self.engines.decision_engine.build_trace(
            DecisionEngineInput(
                decision=decision,
                beliefs=beliefs,
                risk_aversion=ra,
                minimum_margin=mm,
                max_critical_uncertainty=mcu,
                convergence_status=pre_convergence.status,
                convergence_reason=pre_convergence.reason,
            ),
            decision_result,
        )
        self.repo.save_decision_trace(decision_trace)

        sensitivity: DecisionSensitivity | None = None
        if self.engines.decision_sensitivity_engine is not None:
            sensitivity = self.engines.decision_sensitivity_engine.compute(
                decision, beliefs, decision_result
            )
            self.repo.save_decision_sensitivity(sensitivity)
            if self.bus is not None:
                self.bus.publish(
                    make_event(
                        EventType.DECISION_SENSITIVITY_COMPUTED,
                        "decision",
                        decision.id,
                        {"robustness": sensitivity.robustness, "flips": len(sensitivity.flips)},
                    )
                )
        return decision_result, convergence, decision_trace, sensitivity
