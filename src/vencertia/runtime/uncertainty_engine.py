"""UncertaintyEngine — decision-critical uncertainty ranking.

impact(b) = |coef(best, b) − coef(second, b)| × uncertainty(b)
The best/second options are the top two by adjusted utility (docs/decision-engine.md).

v1.2 (V-1/V-5): coefficients are read via :func:`option_coefficients` so
``belief_parameters`` override ``belief_coefficients``. When an option carries
``utility_components``, hard constraints (AND_GATE/THRESHOLD/MINIMUM_REQUIRED)
run BEFORE additive/multiplicative terms — a structurally infeasible option can
never score a linear high.
"""

from __future__ import annotations

from vencertia.domain import Belief, CriticalUncertainty, Decision, DecisionOption, OptionScore


def option_coefficients(option: DecisionOption) -> dict[str, float]:
    """Return the effective coefficient map for an option (V-1).

    ``belief_coefficients`` is the base; ``belief_parameters`` values override
    on key collision. Options without ``belief_parameters`` return the original
    ``belief_coefficients`` contents.
    """
    return option.effective_belief_coefficients


def _score_with_utility_components(
    option: DecisionOption,
    bm: dict[str, Belief],
    risk_aversion: float,
) -> OptionScore:
    """Score an option through its explicit utility components (V-5)."""
    eu = option.base_utility
    uncertainty = 0.0
    multiplicative = 1.0
    blocked = False
    for component in option.utility_components or []:
        belief = bm.get(component.belief_id)
        if belief is None:
            continue
        relation = (
            component.relation_type.value
            if hasattr(component.relation_type, "value")
            else str(component.relation_type)
        )
        if relation in ("AND_GATE", "THRESHOLD", "MINIMUM_REQUIRED"):
            threshold = component.threshold if component.threshold is not None else 0.5
            if belief.probability < threshold:
                blocked = True
        elif relation == "ADDITIVE":
            eu += component.coefficient * belief.probability
            uncertainty += abs(component.coefficient) * belief.uncertainty
        elif relation == "MULTIPLICATIVE":
            multiplicative *= component.coefficient * belief.probability
    eu = eu * multiplicative
    penalty = risk_aversion * uncertainty + option.irreversible_cost + option.opportunity_cost
    adjusted = float("-inf") if blocked else eu - penalty
    return OptionScore(
        option_id=option.id,
        expected_utility=eu,
        uncertainty_penalty=penalty,
        adjusted_utility=adjusted,
    )


def compute_option_scores(
    decision: Decision,
    beliefs: list[Belief],
    risk_aversion: float = 0.25,
) -> list[OptionScore]:
    """Pure expected-utility scoring shared by DecisionEngine and UncertaintyEngine."""
    bm = {b.id: b for b in beliefs}
    scores: list[OptionScore] = []
    for option in decision.options:
        if option.utility_components is None:
            # Original linear path (V-1: read effective coefficients).
            coefficients = option_coefficients(option)
            eu = option.base_utility + sum(
                coefficient * bm[bid].probability
                for bid, coefficient in coefficients.items()
                if bid in bm
            )
            uncertainty = sum(
                abs(coefficient) * bm[bid].uncertainty
                for bid, coefficient in coefficients.items()
                if bid in bm
            )
            penalty = risk_aversion * uncertainty + option.irreversible_cost + option.opportunity_cost
            scores.append(
                OptionScore(
                    option_id=option.id,
                    expected_utility=eu,
                    uncertainty_penalty=penalty,
                    adjusted_utility=eu - penalty,
                )
            )
        else:
            scores.append(_score_with_utility_components(option, bm, risk_aversion))
    scores.sort(key=lambda s: s.adjusted_utility, reverse=True)
    return scores


class UncertaintyEngine:
    """Ranks beliefs by their impact on the best-vs-second decision."""

    def rank(
        self,
        decision: Decision,
        beliefs: list[Belief],
        option_scores: list[OptionScore] | None = None,
    ) -> list[CriticalUncertainty]:
        if option_scores is None:
            option_scores = compute_option_scores(decision, beliefs)
        if len(option_scores) < 2:
            return []
        best = option_scores[0]
        second = option_scores[1]
        best_option = self._option(decision, best.option_id)
        second_option = self._option(decision, second.option_id)
        if best_option is None or second_option is None:
            return []

        best_coefs = option_coefficients(best_option)
        second_coefs = option_coefficients(second_option)
        impacts: list[CriticalUncertainty] = []
        for belief in beliefs:
            delta = abs(
                best_coefs.get(belief.id, 0.0)
                - second_coefs.get(belief.id, 0.0)
            )
            impact = delta * belief.uncertainty
            if delta > 0 or impact > 0:
                impacts.append(
                    CriticalUncertainty(
                        belief_id=belief.id,
                        statement=belief.statement,
                        impact=round(impact, 6),
                        uncertainty=round(belief.uncertainty, 6),
                        coefficient_delta=round(delta, 6),
                    )
                )
        impacts.sort(key=lambda c: c.impact, reverse=True)
        return impacts

    @staticmethod
    def _option(decision: Decision, option_id: str) -> DecisionOption | None:
        for option in decision.options:
            if option.id == option_id:
                return option
        return None
