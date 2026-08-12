"""DecisionSensitivityEngine — flip thresholds + STRONG/FRAGILE verdict (v1.1).

Pure function: for each decision-relevant belief, step p across [0,1] and
recompute option scores to find the nearest recommendation-flip threshold.
"""

from __future__ import annotations

from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Decision,
    DecisionResult,
    DecisionSensitivity,
    FlipThreshold,
    utcnow,
)
from vencertia.runtime.uncertainty_engine import compute_option_scores


class DecisionSensitivityEngine:
    """Computes belief flip thresholds and decision robustness."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def compute(
        self,
        decision: Decision,
        beliefs: list[Belief],
        decision_result: DecisionResult,
    ) -> DecisionSensitivity:
        current_rec = decision_result.recommended_option_id
        step = self.settings.sensitivity_step
        flips: list[FlipThreshold] = []
        relevant = set(decision.relevant_belief_ids or [])

        for belief in beliefs:
            if belief.id not in relevant:
                continue
            current = belief.probability
            nearest: FlipThreshold | None = None
            nearest_distance = float("inf")
            p = 0.0
            while p <= 1.0 + 1e-9:
                if abs(p - current) < step / 2.0:
                    p += step
                    continue
                test_beliefs = [
                    self._with_probability(b, p) if b.id == belief.id else b for b in beliefs
                ]
                scores = compute_option_scores(decision, test_beliefs)
                if len(scores) < 2:
                    p += step
                    continue
                rec = scores[0].option_id
                if rec != current_rec:
                    distance = abs(p - current)
                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest = FlipThreshold(
                            belief_id=belief.id,
                            claim_id=belief.claim_id,
                            current_value=round(current, 6),
                            threshold_value=round(p, 6),
                            would_become=rec,
                            direction="rises_above" if p > current else "falls_below",
                        )
                p += step
            if nearest is not None:
                flips.append(nearest)

        flips.sort(key=lambda f: abs(f.threshold_value - f.current_value))
        margin = float(decision_result.decision_margin or 0.0)
        fragile = margin < self.settings.robustness_margin_threshold or any(
            abs(f.threshold_value - f.current_value) < 0.10 for f in flips
        )
        robustness = "FRAGILE_DECISION" if fragile else "STRONG_DECISION"
        what = [
            (
                f"IF {f.belief_id} {f.direction} to {f.threshold_value:.2f} "
                f"(currently {f.current_value:.2f}), recommendation becomes {f.would_become}."
            )
            for f in flips
        ]
        if not what and robustness == "STRONG_DECISION":
            what.append("No nearby belief flip threshold; decision is robust to belief changes.")
        elif not what:
            what.append("No flip threshold found; decision depends on margin only.")

        return DecisionSensitivity(
            id="DS_" + uuid4().hex,
            decision_id=decision.id,
            current_recommendation=current_rec or "ABSTAIN",
            flips=flips,
            robustness=robustness,
            what_could_change_my_mind=what,
            computed_at=utcnow(),
        )

    @staticmethod
    def _with_probability(belief: Belief, probability: float) -> Belief:
        copy = belief.model_copy(deep=True)
        object.__setattr__(copy, "probability", max(0.0, min(1.0, probability)))
        return copy
