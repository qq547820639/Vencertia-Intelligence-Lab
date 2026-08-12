"""Decision sensitivity tests (v1.1)."""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import Belief, Decision, DecisionOption, DecisionResult
from vencertia.runtime.decision_sensitivity import DecisionSensitivityEngine
from vencertia.runtime.uncertainty_engine import compute_option_scores


def _decision() -> Decision:
    return Decision(
        id="DEC_S", decision_question="Should we commit?", objective_id="OBJ_S", project_id="PRJ_S",
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


def _result(decision, belief, status: str) -> DecisionResult:
    scores = compute_option_scores(decision, [belief])
    return DecisionResult(
        decision_id=decision.id, status=status,
        recommended_option_id=scores[0].option_id, confidence=0.5,
        decision_margin=scores[0].adjusted_utility - scores[1].adjusted_utility,
        option_scores=scores,
    )


def test_sensitivity_finds_flip_thresholds():
    settings = Settings(sensitivity_step=0.01)
    engine = DecisionSensitivityEngine(settings)
    decision = _decision()
    belief = _belief(0.42)
    result = _result(decision, belief, "HOLD")
    sensitivity = engine.compute(decision, [belief], result)
    # At p=0.42 HOLD wins (base 0.35 vs go 0.1+0.8*0.42-0.2=0.236); a rise above
    # ~0.64 flips to GO, a fall keeps HOLD (margin-dependent).
    assert sensitivity.decision_id == decision.id
    assert sensitivity.robustness in ("ROBUST_DECISION", "MODERATE_DECISION", "FRAGILE_DECISION")
    assert sensitivity.flips is not None
    assert sensitivity.what_could_change_my_mind


def test_sensitivity_flip_direction_semantics():
    """WTP 0.42 scenario: falls_below → HOLD-ish, rises_above → GO."""
    settings = Settings(sensitivity_step=0.01)
    engine = DecisionSensitivityEngine(settings)
    decision = _decision()
    belief = _belief(0.42)
    result = _result(decision, belief, "HOLD")
    sensitivity = engine.compute(decision, [belief], result)
    for flip in sensitivity.flips:
        if flip.direction == "rises_above":
            assert flip.threshold_value > flip.current_value
            assert flip.would_become == "go"
        if flip.direction == "falls_below":
            assert flip.threshold_value < flip.current_value


def test_sensitivity_strong_when_no_nearby_flip():
    settings = Settings(sensitivity_step=0.01, fragile_margin=0.05)
    engine = DecisionSensitivityEngine(settings)
    decision = Decision(
        id="DEC_S2", decision_question="q", objective_id="OBJ_S", project_id="PRJ_S",
        options=[
            DecisionOption(id="a", label="a", base_utility=0.9, belief_coefficients={"wtp": 0.01}),
            DecisionOption(id="b", label="b", base_utility=0.1, belief_coefficients={"wtp": -0.01}),
        ],
        relevant_belief_ids=["wtp"],
    )
    belief = _belief(0.5)
    result = _result(decision, belief, "GO")
    sensitivity = engine.compute(decision, [belief], result)
    assert sensitivity.robustness == "ROBUST_DECISION"
