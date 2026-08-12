"""QA v1.1.1 Iteration 2 — adversarial edge cases for robustness (GAP-03).

Targets (QA task list):
  9. robustness threshold boundary: flip distance exactly equal to fragile /
     moderate threshold; margin exactly equal to fragile/moderate margin
 10. sensitivity None/infinity: no finite flip → flip_distance None, no crash,
     JSON round-trip works
"""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import Belief, Decision, DecisionOption, DecisionResult
from vencertia.runtime.decision_sensitivity import DecisionSensitivityEngine
from vencertia.runtime.uncertainty_engine import compute_option_scores


def _belief(bid: str = "wtp", p: float = 0.5, claim_id: str = "CLM_WTP") -> Belief:
    return Belief(
        id=bid, claim_id=claim_id, statement=bid, scope="PROJECT",
        probability=p, posterior=p, alpha=1.0, beta=1.0, uncertainty=0.0,
        decision_relevant=True,
    )


def _engine(**kwargs) -> DecisionSensitivityEngine:
    return DecisionSensitivityEngine(Settings(sensitivity_step=0.01, **kwargs))


def _decision(options: list[DecisionOption], relevant: list[str]) -> Decision:
    return Decision(
        id="DEC_EDGE2", decision_question="q", objective_id="OBJ_E2",
        project_id="PRJ_E2", options=options, relevant_belief_ids=relevant,
    )


# ---------------------------------------------------------------------------
# 9. robustness threshold boundaries (strict < semantics)
# ---------------------------------------------------------------------------


def test_classify_margin_exactly_equal_fragile_margin_is_moderate():
    """margin == fragile_margin (0.05) is NOT < fragile_margin → not fragile;
    margin < moderate_margin (0.12) → MODERATE."""
    engine = _engine()
    assert engine._classify(margin=0.05, min_flip_distance=None, critical_uncertainty=0.0) == (
        "MODERATE_DECISION"
    )


def test_classify_margin_exactly_equal_moderate_margin_is_robust():
    """margin == moderate_margin (0.12) is NOT < moderate_margin → ROBUST."""
    engine = _engine()
    assert engine._classify(margin=0.12, min_flip_distance=None, critical_uncertainty=0.0) == (
        "ROBUST_DECISION"
    )


def test_classify_flip_distance_exactly_equal_fragile_threshold_is_moderate():
    """flip distance == fragile_flip_threshold (0.10) is NOT < threshold →
    not fragile; below moderate_flip_threshold → MODERATE."""
    engine = _engine()
    assert engine._classify(margin=0.20, min_flip_distance=0.10, critical_uncertainty=0.0) == (
        "MODERATE_DECISION"
    )


def test_classify_flip_distance_exactly_equal_moderate_threshold_is_robust():
    """flip distance == moderate_flip_threshold (0.25) is NOT < threshold →
    ROBUST (strict <)."""
    engine = _engine()
    assert engine._classify(margin=0.30, min_flip_distance=0.25, critical_uncertainty=0.0) == (
        "ROBUST_DECISION"
    )


def test_classify_flip_distance_just_below_moderate_threshold_is_moderate():
    engine = _engine()
    assert engine._classify(margin=0.30, min_flip_distance=0.249999, critical_uncertainty=0.0) == (
        "MODERATE_DECISION"
    )


def test_classify_critical_uncertainty_exactly_at_gate_is_not_fragile():
    """critical_uncertainty == max_critical_uncertainty (0.45) is NOT > gate →
    not fragile by uncertainty."""
    engine = _engine()
    assert engine._classify(margin=0.30, min_flip_distance=None, critical_uncertainty=0.45) == (
        "ROBUST_DECISION"
    )


# ---------------------------------------------------------------------------
# 10. sensitivity None/infinity — no finite flip must not crash
# ---------------------------------------------------------------------------


def test_no_finite_flip_sensitivity_serializes_to_json():
    """A DecisionSensitivity with no flips (min_flip_distance=None) must
    serialize to JSON for API emission without crashing."""
    decision = _decision(
        [
            DecisionOption(id="a", label="a", base_utility=0.9,
                           belief_coefficients={"wtp": 0.01}),
            DecisionOption(id="b", label="b", base_utility=0.1,
                           belief_coefficients={"wtp": -0.01}),
        ],
        ["wtp"],
    )
    belief = _belief(p=0.5)
    result = compute_option_scores(decision, [belief])
    decision_result = DecisionResult(
        decision_id=decision.id, status="GO",
        recommended_option_id=result[0].option_id, confidence=0.5,
        decision_margin=result[0].adjusted_utility - result[1].adjusted_utility,
        option_scores=result,
    )
    sensitivity = _engine().compute(decision, [belief], decision_result)
    assert sensitivity.flips == []
    assert sensitivity.robustness == "ROBUST_DECISION"
    dumped = sensitivity.model_dump(mode="json")
    assert dumped["flips"] == []
    assert dumped["robustness"] == "ROBUST_DECISION"
    # Re-parse round-trip (what an API client would do).
    from vencertia.domain import DecisionSensitivity

    restored = DecisionSensitivity.model_validate(dumped)
    assert restored.robustness == "ROBUST_DECISION"
    assert restored.flips == []


def test_sensitivity_compute_with_empty_beliefs_does_not_crash():
    """Empty relevant beliefs → no flips, still returns a valid sensitivity."""
    decision = _decision(
        [
            DecisionOption(id="a", label="a", base_utility=0.9, belief_coefficients={}),
            DecisionOption(id="b", label="b", base_utility=0.1, belief_coefficients={}),
        ],
        [],
    )
    sensitivity = _engine().compute(decision, [], DecisionResult(
        decision_id=decision.id, status="GO", recommended_option_id="a",
        confidence=0.5, decision_margin=0.8, option_scores=[],
    ))
    assert sensitivity.flips == []
    assert sensitivity.robustness == "ROBUST_DECISION"
