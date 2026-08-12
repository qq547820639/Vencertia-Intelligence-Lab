"""Three-level robustness edge tests (GAP-03, v1.1.1).

Verdicts: ROBUST_DECISION / MODERATE_DECISION / FRAGILE_DECISION.
Legacy STRONG_DECISION maps to ROBUST_DECISION via normalize_robustness.
"""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.domain import Belief, Decision, DecisionOption, DecisionResult
from vencertia.runtime.decision_sensitivity import (
    DecisionSensitivityEngine,
    normalize_robustness,
)
from vencertia.runtime.uncertainty_engine import compute_option_scores


def _belief(bid: str = "wtp", p: float = 0.5, claim_id: str = "CLM_WTP") -> Belief:
    return Belief(
        id=bid, claim_id=claim_id, statement=bid, scope="PROJECT",
        probability=p, posterior=p, alpha=1.0, beta=1.0, uncertainty=0.0,
        decision_relevant=True,
    )


def _result(decision, beliefs, status: str = "GO", rec: str | None = None) -> DecisionResult:
    scores = compute_option_scores(decision, beliefs)
    return DecisionResult(
        decision_id=decision.id, status=status,
        recommended_option_id=rec or scores[0].option_id, confidence=0.5,
        decision_margin=scores[0].adjusted_utility - scores[1].adjusted_utility,
        option_scores=scores,
    )


def _engine(**kwargs) -> DecisionSensitivityEngine:
    return DecisionSensitivityEngine(
        Settings(sensitivity_step=0.01, **kwargs)
    )


def _decision(options: list[DecisionOption], relevant: list[str]) -> Decision:
    return Decision(
        id="DEC_EDGE", decision_question="q", objective_id="OBJ_E", project_id="PRJ_E",
        options=options, relevant_belief_ids=relevant,
    )


# ---------------------------------------------------------------------------
# 1. no finite flip
# ---------------------------------------------------------------------------


def test_no_finite_flip_is_robust():
    decision = _decision(
        [
            DecisionOption(id="a", label="a", base_utility=0.9, belief_coefficients={"wtp": 0.01}),
            DecisionOption(id="b", label="b", base_utility=0.1, belief_coefficients={"wtp": -0.01}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.5)
    sensitivity = _engine().compute(decision, [belief], _result(decision, [belief]))
    assert sensitivity.flips == []
    assert sensitivity.robustness == "ROBUST_DECISION"


def test_legacy_string_maps_to_robust():
    assert normalize_robustness("STRONG_DECISION") == "ROBUST_DECISION"
    assert normalize_robustness("MODERATE_DECISION") == "MODERATE_DECISION"
    assert normalize_robustness("FRAGILE_DECISION") == "FRAGILE_DECISION"
    assert normalize_robustness(None) == "FRAGILE_DECISION"


# ---------------------------------------------------------------------------
# 2. already abstaining
# ---------------------------------------------------------------------------


def test_already_abstaining_has_no_flips_and_is_fragile():
    decision = _decision(
        [
            DecisionOption(id="go", label="Go", base_utility=0.1, belief_coefficients={"wtp": 0.8},
                           irreversible_cost=0.2),
            DecisionOption(id="hold", label="Hold", base_utility=0.35, belief_coefficients={"wtp": 0.1}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.42)
    result = DecisionResult(
        decision_id=decision.id, status="ABSTAIN", recommended_option_id=None,
        confidence=0.0, decision_margin=0.0, option_scores=[],
    )
    sensitivity = _engine().compute(decision, [belief], result)
    assert sensitivity.flips == []
    assert sensitivity.current_recommendation == "ABSTAIN"
    assert any("abstaining" in line for line in sensitivity.what_could_change_my_mind)
    # Zero margin → fragile by margin policy (no fake robustness).
    assert sensitivity.robustness == "FRAGILE_DECISION"


# ---------------------------------------------------------------------------
# 3. single dominant belief
# ---------------------------------------------------------------------------


def test_single_dominant_belief_classifies_moderate():
    decision = _decision(
        [
            DecisionOption(id="go", label="Go", base_utility=0.1, belief_coefficients={"wtp": 0.8},
                           irreversible_cost=0.2),
            DecisionOption(id="hold", label="Hold", base_utility=0.35, belief_coefficients={"wtp": 0.1}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.42)
    sensitivity = _engine().compute(decision, [belief], _result(decision, [belief], "HOLD", "hold"))
    assert len(sensitivity.flips) == 1
    flip = sensitivity.flips[0]
    assert flip.belief_id == "wtp"
    assert flip.direction == "rises_above"
    # Flip distance ~0.23 (< moderate_flip_threshold 0.25) but >= fragile 0.10.
    distance = abs(flip.threshold_value - flip.current_value)
    assert 0.10 <= distance < 0.25
    assert sensitivity.robustness == "MODERATE_DECISION"


# ---------------------------------------------------------------------------
# 4. two equal criticals
# ---------------------------------------------------------------------------


def test_two_equal_critical_beliefs_both_reported():
    decision = _decision(
        [
            DecisionOption(id="go", label="Go", base_utility=0.1,
                           belief_coefficients={"b1": 0.8, "b2": 0.8}, irreversible_cost=0.2),
            DecisionOption(id="hold", label="Hold", base_utility=0.35,
                           belief_coefficients={"b1": 0.1, "b2": 0.1}),
        ],
        ["b1", "b2"],
    )
    beliefs = [_belief("b1", 0.42, "CLM_1"), _belief("b2", 0.42, "CLM_2")]
    sensitivity = _engine().compute(decision, beliefs, _result(decision, beliefs))
    assert {f.belief_id for f in sensitivity.flips} == {"b1", "b2"}
    distances = {round(abs(f.threshold_value - f.current_value), 6) for f in sensitivity.flips}
    assert len(distances) == 1  # equal critical distances
    # Both flips moderately close (0.20) → MODERATE (not fragile: >= 0.10).
    assert sensitivity.robustness == "MODERATE_DECISION"


# ---------------------------------------------------------------------------
# 5. very large margin
# ---------------------------------------------------------------------------


def test_very_large_margin_is_robust():
    decision = _decision(
        [
            DecisionOption(id="a", label="a", base_utility=0.9, belief_coefficients={"wtp": 0.01}),
            DecisionOption(id="b", label="b", base_utility=0.1, belief_coefficients={"wtp": -0.01}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.5)
    sensitivity = _engine().compute(decision, [belief], _result(decision, [belief]))
    assert sensitivity.robustness == "ROBUST_DECISION"


# ---------------------------------------------------------------------------
# 6. tiny margin
# ---------------------------------------------------------------------------


def test_tiny_margin_is_fragile():
    decision = _decision(
        [
            DecisionOption(id="go", label="Go", base_utility=0.0, belief_coefficients={"wtp": 0.8},
                           irreversible_cost=0.2),
            DecisionOption(id="hold", label="Hold", base_utility=0.12, belief_coefficients={"wtp": 0.1}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.5)
    result = _result(decision, [belief], "GO", "go")
    assert result.decision_margin < 0.05  # sanity: tiny margin
    sensitivity = _engine().compute(decision, [belief], result)
    assert sensitivity.robustness == "FRAGILE_DECISION"


# ---------------------------------------------------------------------------
# 7. flip exactly on the fragile threshold
# ---------------------------------------------------------------------------


def test_flip_exactly_on_fragile_threshold_is_moderate_not_fragile():
    """A flip at distance == fragile_flip_threshold (0.10) is NOT fragile
    (strict <), but is below moderate_flip_threshold → MODERATE."""
    decision = _decision(
        [
            # go(p) = 0 + 1.0*p - 0.4 = p - 0.4  (flips vs hold at p=0.60)
            DecisionOption(id="go", label="Go", base_utility=0.0, belief_coefficients={"wtp": 1.0},
                           irreversible_cost=0.4),
            # hold(p) = 0.32 - 0.2*p  → hold wins at p=0.5, tie at p=0.60
            DecisionOption(id="hold", label="Hold", base_utility=0.32, belief_coefficients={"wtp": -0.2}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.5)
    result = _result(decision, [belief], "HOLD", "hold")
    sensitivity = _engine().compute(decision, [belief], result)
    assert sensitivity.flips
    distance = abs(sensitivity.flips[0].threshold_value - sensitivity.flips[0].current_value)
    assert distance == pytest.approx(0.10, abs=0.011)
    assert sensitivity.robustness == "MODERATE_DECISION"


# ---------------------------------------------------------------------------
# robustness policy uses all three signals
# ---------------------------------------------------------------------------


def test_critical_uncertainty_above_gate_is_fragile():
    decision = _decision(
        [
            DecisionOption(id="a", label="a", base_utility=0.9, belief_coefficients={"wtp": 0.01}),
            DecisionOption(id="b", label="b", base_utility=0.1, belief_coefficients={"wtp": -0.01}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.5)
    scores = compute_option_scores(decision, [belief])
    result = DecisionResult(
        decision_id=decision.id, status="GO", recommended_option_id=scores[0].option_id,
        confidence=0.5,
        decision_margin=scores[0].adjusted_utility - scores[1].adjusted_utility,
        option_scores=scores,
        critical_uncertainty=0.9,  # above max_critical_uncertainty 0.45
    )
    sensitivity = _engine().compute(decision, [belief], result)
    assert sensitivity.robustness == "FRAGILE_DECISION"
