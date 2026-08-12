"""UncertaintyEngine tests: decision-impact ranking."""

from __future__ import annotations

from vencertia.domain import Belief, Decision, DecisionOption
from vencertia.runtime.uncertainty_engine import UncertaintyEngine


def _belief(bid, unc) -> Belief:
    return Belief(
        id=bid, claim_id="CLM_" + bid, statement=bid, scope="PROJECT",
        project_id="PRJ_1", posterior=0.5, probability=0.5, alpha=1.0, beta=1.0,
        uncertainty=unc, decision_relevant=True,
    )


def _decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[
            DecisionOption(id="a", label="a", base_utility=0.0,
                           belief_coefficients={"wtp": 0.9, "problem": 0.2}),
            DecisionOption(id="b", label="b", base_utility=0.0,
                           belief_coefficients={"wtp": -0.1, "problem": -0.4}),
        ],
        relevant_belief_ids=["wtp", "problem"],
    )


def test_rank_orders_by_decision_impact():
    engine = UncertaintyEngine()
    beliefs = [_belief("wtp", 0.8), _belief("problem", 0.5)]
    ranked = engine.rank(_decision(), beliefs)
    assert ranked[0].belief_id == "wtp"  # delta 1.0 * 0.8 = 0.8
    assert ranked[1].belief_id == "problem"  # delta 0.6 * 0.5 = 0.3
    assert ranked[0].impact > ranked[1].impact


def test_rank_includes_coefficient_delta():
    engine = UncertaintyEngine()
    ranked = engine.rank(_decision(), [_belief("wtp", 0.8)])
    assert abs(ranked[0].coefficient_delta - 1.0) < 1e-9
    assert abs(ranked[0].impact - 0.8) < 1e-9


def test_rank_returns_empty_for_single_option():
    decision = Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a")], relevant_belief_ids=[],
    )
    assert UncertaintyEngine().rank(decision, [_belief("wtp", 0.8)]) == []
