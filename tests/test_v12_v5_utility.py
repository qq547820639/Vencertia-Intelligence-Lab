"""v1.2 V-5 utility relation type acceptance tests."""

from __future__ import annotations

import math

from tests.conftest import make_belief
from vencertia.domain import Decision, DecisionOption, UtilityComponent, UtilityRelationType
from vencertia.runtime.uncertainty_engine import compute_option_scores


def _decision(options: list[DecisionOption]) -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=options, relevant_belief_ids=["wtp", "distribution"],
    )


def _score_for(scores, option_id: str):
    return next(s for s in scores if s.option_id == option_id)


def test_and_gate_blocks_below_threshold():
    beliefs = [make_belief("wtp", 0.4, 4, 6)]
    option = DecisionOption(
        id="a", label="a", base_utility=1.0,
        utility_components=[
            UtilityComponent(
                belief_id="wtp", relation_type=UtilityRelationType.AND_GATE, threshold=0.6,
            )
        ],
    )
    scores = compute_option_scores(
        _decision([option, DecisionOption(id="b", label="b", base_utility=0.0)]), beliefs
    )
    score_a = _score_for(scores, "a")
    assert math.isinf(score_a.adjusted_utility)
    assert score_a.adjusted_utility < 0


def test_and_gate_passes_above_threshold():
    beliefs = [make_belief("wtp", 0.8, 8, 2)]
    option = DecisionOption(
        id="a", label="a", base_utility=1.0,
        utility_components=[
            UtilityComponent(
                belief_id="wtp", relation_type=UtilityRelationType.AND_GATE, threshold=0.6,
            )
        ],
    )
    scores = compute_option_scores(
        _decision([option, DecisionOption(id="b", label="b", base_utility=0.0)]), beliefs
    )
    score_a = _score_for(scores, "a")
    assert not math.isinf(score_a.adjusted_utility)


def test_none_components_matches_legacy_linear_path():
    beliefs = [make_belief("wtp", 0.8, 8, 2)]
    linear = _decision([
        DecisionOption(id="a", label="a", belief_coefficients={"wtp": 0.5}),
        DecisionOption(id="b", label="b", belief_coefficients={"wtp": -0.3}),
    ])
    none_components = _decision([
        DecisionOption(
            id="a", label="a", belief_coefficients={"wtp": 0.5}, utility_components=None,
        ),
        DecisionOption(
            id="b", label="b", belief_coefficients={"wtp": -0.3}, utility_components=None,
        ),
    ])
    assert [s.adjusted_utility for s in compute_option_scores(linear, beliefs)] == [
        s.adjusted_utility for s in compute_option_scores(none_components, beliefs)
    ]


def test_threshold_constraint_precedes_additive():
    """High WTP would score linearly, but a failed THRESHOLD blocks it first."""
    beliefs = [
        make_belief("wtp", 0.9, 36, 4),
        make_belief("distribution", 0.05, 1, 19),
    ]
    option = DecisionOption(
        id="a", label="a", base_utility=0.0,
        utility_components=[
            UtilityComponent(
                belief_id="distribution",
                relation_type=UtilityRelationType.THRESHOLD,
                threshold=0.6,
            ),
            UtilityComponent(
                belief_id="wtp",
                relation_type=UtilityRelationType.ADDITIVE,
                coefficient=0.85,
            ),
        ],
    )
    scores = compute_option_scores(
        _decision([option, DecisionOption(id="b", label="b", base_utility=0.0)]), beliefs
    )
    score_a = _score_for(scores, "a")
    assert math.isinf(score_a.adjusted_utility)
    assert score_a.adjusted_utility < 0
