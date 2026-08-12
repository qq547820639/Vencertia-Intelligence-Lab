"""QA adversarial tests — Decision sensitivity flip thresholds + robustness (P0).

Verifies flip thresholds numerically and STRONG vs FRAGILE distinction.
"""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.domain import Belief, Decision, DecisionOption, DecisionResult
from vencertia.runtime.decision_sensitivity import DecisionSensitivityEngine
from vencertia.runtime.uncertainty_engine import compute_option_scores


def _decision() -> Decision:
    return Decision(
        id="DEC_QA_S", decision_question="Should we commit?", objective_id="OBJ_S", project_id="PRJ_S",
        options=[
            DecisionOption(id="go", label="Go", kind="GO", base_utility=0.1,
                           belief_coefficients={"wtp": 0.8}, irreversible_cost=0.2),
            DecisionOption(id="hold", label="Hold", kind="HOLD", base_utility=0.35,
                           belief_coefficients={"wtp": 0.1}),
        ],
        relevant_belief_ids=["wtp"],
    )


def _belief(p=0.42) -> Belief:
    return Belief(
        id="wtp", claim_id="CLM_WTP", statement="willingness to pay", scope="PROJECT",
        probability=p, posterior=p, alpha=1.0, beta=1.0, uncertainty=0.3,
        decision_relevant=True,
    )


def _result(decision, belief, status="HOLD") -> DecisionResult:
    scores = compute_option_scores(decision, [belief])
    return DecisionResult(
        decision_id=decision.id, status=status,
        recommended_option_id=scores[0].option_id, confidence=0.5,
        decision_margin=scores[0].adjusted_utility - scores[1].adjusted_utility,
        option_scores=scores,
    )


def test_qa_flip_threshold_rises_above_to_go():
    """At WTP=0.42 recommendation is HOLD; a rise must flip to GO at a specific threshold."""
    engine = DecisionSensitivityEngine(Settings(sensitivity_step=0.01))
    decision = _decision()
    belief = _belief(0.42)
    result = _result(decision, belief, "HOLD")
    assert result.recommended_option_id == "hold"  # sanity: current rec is HOLD
    sensitivity = engine.compute(decision, [belief], result)
    rises = [f for f in sensitivity.flips if f.direction == "rises_above"]
    assert rises, f"expected a rises_above flip, got flips={sensitivity.flips}"
    flip = min(rises, key=lambda f: abs(f.threshold_value - f.current_value))
    # The nearest rise flip must be ABOVE the current value and point to GO.
    assert flip.threshold_value > flip.current_value
    assert flip.would_become == "go"
    assert flip.current_value == pytest.approx(0.42)


def test_qa_flip_threshold_direction_semantics():
    """falls_below flips stay below current; rises_above stay above."""
    engine = DecisionSensitivityEngine(Settings(sensitivity_step=0.01))
    decision = _decision()
    belief = _belief(0.42)
    sensitivity = engine.compute(decision, [belief], _result(decision, belief))
    for f in sensitivity.flips:
        if f.direction == "rises_above":
            assert f.threshold_value > f.current_value
        if f.direction == "falls_below":
            assert f.threshold_value < f.current_value


def test_qa_robustness_strong_vs_fragile():
    """Robust: no nearby flip and healthy margin -> STRONG; else FRAGILE."""
    settings = Settings(sensitivity_step=0.01, robustness_margin_threshold=0.05)
    engine = DecisionSensitivityEngine(settings)

    # STRONG: option utilities barely depend on the belief -> no flip nearby.
    strong_decision = Decision(
        id="DEC_S2", decision_question="q", objective_id="OBJ_S", project_id="PRJ_S",
        options=[
            DecisionOption(id="a", label="a", base_utility=0.9, belief_coefficients={"wtp": 0.01}),
            DecisionOption(id="b", label="b", base_utility=0.1, belief_coefficients={"wtp": -0.01}),
        ],
        relevant_belief_ids=["wtp"],
    )
    strong = engine.compute(strong_decision, [_belief(0.5)], _result(strong_decision, _belief(0.5)))
    assert strong.robustness == "STRONG_DECISION"

    # FRAGILE: belief strongly drives the decision with a nearby flip threshold
    # and a thin margin at the current p.
    fragile_decision = Decision(
        id="DEC_FRAG", decision_question="q", objective_id="OBJ_S", project_id="PRJ_S",
        options=[
            DecisionOption(id="go", label="Go", kind="GO", base_utility=0.0,
                           belief_coefficients={"wtp": 0.8}, irreversible_cost=0.2),
            DecisionOption(id="hold", label="Hold", kind="HOLD", base_utility=0.1,
                           belief_coefficients={"wtp": 0.1}),
        ],
        relevant_belief_ids=["wtp"],
    )
    fragile_belief = _belief(0.42)
    fragile_result = _result(fragile_decision, fragile_belief, "HOLD")
    # Sanity: at p=0.42 hold barely wins (margin < 0.05) and go flips nearby.
    assert fragile_result.recommended_option_id == "hold"
    fragile = engine.compute(fragile_decision, [fragile_belief], fragile_result)
    assert fragile.robustness == "FRAGILE_DECISION"
    assert fragile.flips
    assert any(abs(f.threshold_value - f.current_value) < 0.10 for f in fragile.flips)


def test_qa_sensitivity_what_could_change_my_mind_present():
    """Output exposes human-readable what_could_change_my_mind."""
    engine = DecisionSensitivityEngine(Settings(sensitivity_step=0.01))
    sensitivity = engine.compute(_decision(), [_belief(0.42)], _result(_decision(), _belief(0.42)))
    assert sensitivity.what_could_change_my_mind
    assert any("wtp" in line for line in sensitivity.what_could_change_my_mind)
