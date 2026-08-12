"""DecisionSensitivityEngine — flip thresholds + three-level robustness (GAP-03).

Pure function: for each decision-relevant belief, step p across [0,1] and
recompute option scores to find the nearest recommendation-flip threshold.

Robustness policy (v1.1.1) combines:
  * decision margin (``decision_result.decision_margin``)
  * nearest flip distance (``min |threshold - current|`` over flips)
  * critical uncertainty (``decision_result.critical_uncertainty``)

Verdicts: ``ROBUST_DECISION`` / ``MODERATE_DECISION`` / ``FRAGILE_DECISION``.
Legacy strings ``STRONG_DECISION`` → ``ROBUST_DECISION`` are normalized via
:func:`normalize_robustness` (old persisted records stay readable).
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

# Legacy robustness strings → canonical three-level naming (GAP-03).
_ROBUSTNESS_ALIASES: dict[str, str] = {
    "STRONG_DECISION": "ROBUST_DECISION",
    "FRAGILE_DECISION": "FRAGILE_DECISION",
    "MODERATE_DECISION": "MODERATE_DECISION",
}


def normalize_robustness(value: str | None) -> str:
    """Map any legacy robustness string to the canonical three-level naming."""
    if not value:
        return "FRAGILE_DECISION"
    return _ROBUSTNESS_ALIASES.get(value, value)


class DecisionSensitivityEngine:
    """Computes belief flip thresholds and the three-level decision robustness."""

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

        # Already abstaining: there is no recommendation to flip (GAP-03 edge).
        if current_rec is not None:
            flips = self._find_flips(decision, beliefs, decision_result, current_rec, step, relevant)

        flips.sort(key=lambda f: abs(f.threshold_value - f.current_value))
        margin = float(decision_result.decision_margin or 0.0)
        # min flip distance; None means "no finite flip" (handled stably).
        min_flip_distance: float | None = (
            min(abs(f.threshold_value - f.current_value) for f in flips) if flips else None
        )
        critical_uncertainty = float(getattr(decision_result, "critical_uncertainty", 0.0) or 0.0)
        robustness = self._classify(margin, min_flip_distance, critical_uncertainty)
        what = [
            (
                f"IF {f.belief_id} {f.direction} to {f.threshold_value:.2f} "
                f"(currently {f.current_value:.2f}), recommendation becomes {f.would_become}."
            )
            for f in flips
        ]
        if current_rec is None:
            what.append("Decision is abstaining; no recommendation to flip.")
        elif not what and robustness == "ROBUST_DECISION":
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

    def _find_flips(
        self,
        decision: Decision,
        beliefs: list[Belief],
        decision_result: DecisionResult,
        current_rec: str,
        step: float,
        relevant: set[str],
    ) -> list[FlipThreshold]:
        flips: list[FlipThreshold] = []
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
        return flips

    def _classify(
        self,
        margin: float,
        min_flip_distance: float | None,
        critical_uncertainty: float,
    ) -> str:
        """Three-level robustness policy (thresholds from Settings, GAP-03).

        - FRAGILE_DECISION: margin below ``fragile_margin`` OR a flip closer
          than ``fragile_flip_threshold`` (incl. critical uncertainty above
          the decision gate ``max_critical_uncertainty``).
        - MODERATE_DECISION: margin below ``moderate_margin`` OR a flip closer
          than ``moderate_flip_threshold``.
        - ROBUST_DECISION: otherwise.

        ``min_flip_distance=None`` (no finite flip) is handled stably: it can
        never trigger a flip-based downgrade.
        """
        if margin < self.settings.fragile_margin:
            return "FRAGILE_DECISION"
        if min_flip_distance is not None:
            # Round to 6dp so a flip exactly on the threshold (e.g. 0.10) is
            # not downgraded by binary float noise (0.0999999...).
            flip_distance = round(min_flip_distance, 6)
            if flip_distance < self.settings.fragile_flip_threshold:
                return "FRAGILE_DECISION"
        if critical_uncertainty > self.settings.max_critical_uncertainty:
            return "FRAGILE_DECISION"
        if margin < self.settings.moderate_margin:
            return "MODERATE_DECISION"
        if min_flip_distance is not None:
            flip_distance = round(min_flip_distance, 6)
            if flip_distance < self.settings.moderate_flip_threshold:
                return "MODERATE_DECISION"
        return "ROBUST_DECISION"

    @staticmethod
    def _with_probability(belief: Belief, probability: float) -> Belief:
        copy = belief.model_copy(deep=True)
        object.__setattr__(copy, "probability", max(0.0, min(1.0, probability)))
        return copy
