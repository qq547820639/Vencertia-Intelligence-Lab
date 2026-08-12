"""UncertaintyEngine — decision-critical uncertainty ranking.

impact(b) = |coef(best, b) − coef(second, b)| × uncertainty(b)
The best/second options are the top two by adjusted utility (docs/decision-engine.md).
"""

from __future__ import annotations

from vencertia.domain import Belief, CriticalUncertainty, Decision, DecisionOption, OptionScore


def compute_option_scores(
    decision: Decision,
    beliefs: list[Belief],
    risk_aversion: float = 0.25,
) -> list[OptionScore]:
    """Pure expected-utility scoring shared by DecisionEngine and UncertaintyEngine."""
    bm = {b.id: b for b in beliefs}
    scores: list[OptionScore] = []
    for option in decision.options:
        eu = option.base_utility + sum(
            coefficient * bm[bid].probability
            for bid, coefficient in option.belief_coefficients.items()
            if bid in bm
        )
        uncertainty = sum(
            abs(coefficient) * bm[bid].uncertainty
            for bid, coefficient in option.belief_coefficients.items()
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

        impacts: list[CriticalUncertainty] = []
        for belief in beliefs:
            delta = abs(
                best_option.belief_coefficients.get(belief.id, 0.0)
                - second_option.belief_coefficients.get(belief.id, 0.0)
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
