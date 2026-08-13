"""ConvergenceEngine — 7-state convergence judgment (architecture §3.4).

States: NOT_CONVERGED / RESEARCH_MORE / EXPERIMENT_REQUIRED / SEARCH_EXHAUSTED /
CONDITIONALLY_CONVERGED / CONVERGED / EXECUTE.
"""

from __future__ import annotations

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    ConvergenceReport,
    ConvergenceStatus,
    CriticalUncertainty,
    Decision,
    DecisionType,
    Experiment,
)


class ConvergenceEngine:
    """Deterministic convergence state machine."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def check(
        self,
        decision: Decision,
        beliefs: list[Belief],
        critical: list[CriticalUncertainty],
        experiments: list[Experiment] | None = None,
        decision_margin: float | None = None,
        decision_status: DecisionType | None = None,
        research_stop_status: str | None = None,
    ) -> ConvergenceReport:
        threshold = self.settings.max_critical_uncertainty
        experiments = experiments or []
        if decision_status is not None and not hasattr(decision_status, "value"):
            decision_status = DecisionType(decision_status)
        max_impact = max((c.impact for c in critical), default=0.0)
        critical_ids = {c.belief_id for c in critical}

        # v1.1: the ResearchStopRule may declare SEARCH_EXHAUSTED; inject that
        # signal so convergence does not claim cheap research is still useful.
        if research_stop_status == "SEARCH_EXHAUSTED" and max_impact > threshold:
            executable = [
                e
                for e in experiments
                if e.status in (None, "PROPOSED", "RUNNING")
            ]
            if not executable:
                return ConvergenceReport(
                    decision_id=decision.id,
                    status=ConvergenceStatus.SEARCH_EXHAUSTED,
                    reason=(
                        "ResearchStopRule: search exhausted and no executable "
                        "experiment; decide under residual uncertainty."
                    ),
                    critical_uncertainties=critical,
                )

        # Already-resolved decisions.
        if decision_status is not None and decision_status != DecisionType.ABSTAIN:
            if decision_status in (DecisionType.GO, DecisionType.SELECT_OPTION):
                return ConvergenceReport(
                    decision_id=decision.id,
                    status=ConvergenceStatus.EXECUTE,
                    reason="Decision resolved to GO/SELECT_OPTION; ready to execute.",
                    critical_uncertainties=critical,
                )
            if decision_status in (
                DecisionType.HOLD,
                DecisionType.PIVOT,
                DecisionType.KILL,
                DecisionType.CONDITIONAL_GO,
            ):
                status = (
                    ConvergenceStatus.CONDITIONALLY_CONVERGED
                    if decision_status == DecisionType.CONDITIONAL_GO
                    else ConvergenceStatus.CONVERGED
                )
                return ConvergenceReport(
                    decision_id=decision.id,
                    status=status,
                    reason=f"Decision resolved to {decision_status.value}; converged.",
                    critical_uncertainties=critical,
                )

        # No decision-relevant critical uncertainty -> converged.
        if not critical:
            return ConvergenceReport(
                decision_id=decision.id,
                status=ConvergenceStatus.CONVERGED,
                reason="No decision-critical uncertainties remain.",
                critical_uncertainties=critical,
            )

        # Critical uncertainty within threshold -> conditions satisfied path.
        if max_impact <= threshold:
            return ConvergenceReport(
                decision_id=decision.id,
                status=ConvergenceStatus.CONDITIONALLY_CONVERGED,
                reason=(
                    f"Critical uncertainty ({max_impact:.3f}) within threshold "
                    f"({threshold}); conditions may be verified."
                ),
                critical_uncertainties=critical,
            )

        # Cheap research still available targeting critical beliefs.
        cheap_research = [
            e
            for e in experiments
            if e.time <= 2.0 and e.cost <= 1.0 and critical_ids.intersection(e.target_belief_ids)
        ]
        if cheap_research:
            return ConvergenceReport(
                decision_id=decision.id,
                status=ConvergenceStatus.RESEARCH_MORE,
                reason="Low-cost research can still reduce critical uncertainty.",
                critical_uncertainties=critical,
                next_step=cheap_research[0].id,
            )

        # Research exhausted: if an executable experiment exists -> EXPERIMENT_REQUIRED.
        executable = [
            e
            for e in experiments
            if e.status in (None, "PROPOSED", "RUNNING")
        ]
        if executable:
            return ConvergenceReport(
                decision_id=decision.id,
                status=ConvergenceStatus.EXPERIMENT_REQUIRED,
                reason="Research information value is exhausted; a real experiment is required.",
                critical_uncertainties=critical,
                next_step=executable[0].id,
            )

        # No research, no experiment -> decide under residual uncertainty.
        return ConvergenceReport(
            decision_id=decision.id,
            status=ConvergenceStatus.SEARCH_EXHAUSTED,
            reason=(
                "Search exhausted and no executable experiment; "
                "decide under residual uncertainty or define an experiment."
            ),
            critical_uncertainties=critical,
        )
