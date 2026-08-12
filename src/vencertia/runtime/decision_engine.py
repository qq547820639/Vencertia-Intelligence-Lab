"""DecisionEngine — expected utility + penalties + margin + ABSTAIN.

Pure function: never mutates beliefs/decisions (docs/decision-engine.md).
Output uses :class:`DecisionResult` (aliased as DecisionEngineOutput).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    ConvergenceStatus,
    Decision,
    DecisionOption,
    DecisionResult,
    DecisionType,
    Objective,
    OptionScore,
    RuleSet,
)
from vencertia.runtime.uncertainty_engine import UncertaintyEngine, compute_option_scores

DecisionEngineOutput = DecisionResult

# Accept both short and canonical kind values for option semantics.
KIND_NORMALIZATION = {
    "CONDITIONAL": DecisionType.CONDITIONAL_GO,
    "CONDITIONAL_GO": DecisionType.CONDITIONAL_GO,
    "SELECT": DecisionType.SELECT_OPTION,
    "SELECT_OPTION": DecisionType.SELECT_OPTION,
    "KILL": DecisionType.KILL,
    "PIVOT": DecisionType.PIVOT,
    "HOLD": DecisionType.HOLD,
    "GO": DecisionType.GO,
}


@dataclass
class DecisionEngineInput:
    decision: Decision
    beliefs: list[Belief]
    objective: Objective | None = None
    risk_aversion: float = 0.25
    minimum_margin: float = 0.08
    max_critical_uncertainty: float = 0.45
    policy: RuleSet | None = None
    convergence_status: ConvergenceStatus = ConvergenceStatus.NOT_CONVERGED
    convergence_reason: str = ""


class DecisionEngine:
    """Deterministic decision evaluation with explicit ABSTAIN support."""

    def __init__(
        self,
        settings: Settings | None = None,
        uncertainty_engine: UncertaintyEngine | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.uncertainty_engine = uncertainty_engine or UncertaintyEngine()

    def evaluate(self, inp: DecisionEngineInput) -> DecisionResult:
        scores = compute_option_scores(
            inp.decision, inp.beliefs, inp.risk_aversion
        )
        if len(scores) < 2:
            raise ValueError("A decision requires at least two options.")

        best, second = scores[0], scores[1]
        margin = best.adjusted_utility - second.adjusted_utility

        criticals = self.uncertainty_engine.rank(
            inp.decision, inp.beliefs, option_scores=scores
        )
        critical_belief_id = criticals[0].belief_id if criticals else None
        critical_uncertainty = criticals[0].impact if criticals else 0.0

        rationale: list[str] = [
            f"Top option {best.option_id}: adjusted utility={best.adjusted_utility:.4f}.",
            f"Runner-up {second.option_id}: adjusted utility={second.adjusted_utility:.4f}.",
            f"Decision margin={margin:.4f}; critical uncertainty={critical_uncertainty:.4f} "
            f"({critical_belief_id or 'none'}).",
        ]

        confidence = max(
            0.0,
            min(
                1.0,
                0.5
                + 0.35 * min(1.0, abs(margin))
                - 0.35 * critical_uncertainty,
            ),
        )

        abstain = margin < inp.minimum_margin or critical_uncertainty > inp.max_critical_uncertainty
        if abstain:
            status = DecisionType.ABSTAIN
            recommended = None
            rationale.append(
                "Decision has not converged; acquire decision-changing evidence before committing."
            )
        else:
            best_option = self._option(inp.decision, best.option_id)
            status = self._map_decision_type(best_option)
            recommended = best.option_id
            rationale.append("Decision converged under current policy thresholds.")

        return DecisionResult(
            decision_id=inp.decision.id,
            status=status.value if hasattr(status, "value") else str(status),
            recommended_option_id=recommended,
            confidence=round(confidence, 6),
            decision_margin=round(margin, 6),
            option_scores=scores,
            critical_belief_id=critical_belief_id,
            critical_uncertainty=round(critical_uncertainty, 6),
            convergence_status=inp.convergence_status.value
            if hasattr(inp.convergence_status, "value")
            else str(inp.convergence_status),
            rationale=rationale,
        )

    @staticmethod
    def _option(decision: Decision, option_id: str) -> DecisionOption | None:
        for option in decision.options:
            if option.id == option_id:
                return option
        return None

    @staticmethod
    def _map_decision_type(option: DecisionOption) -> DecisionType:
        if option.kind is not None:
            raw = option.kind.value if hasattr(option.kind, "value") else str(option.kind)
            normalized = KIND_NORMALIZATION.get(raw)
            if normalized is not None:
                return normalized
        label = (option.label or option.id or "").lower()
        if "kill" in label or "stop" in label:
            return DecisionType.KILL
        if "pivot" in label:
            return DecisionType.PIVOT
        if "hold" in label or "wait" in label:
            return DecisionType.HOLD
        if "conditional" in label:
            return DecisionType.CONDITIONAL_GO
        if "select" in label:
            return DecisionType.SELECT_OPTION
        return DecisionType.GO
