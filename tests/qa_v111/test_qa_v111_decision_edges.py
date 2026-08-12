"""QA v1.1.1 Iteration 2 — adversarial edge case for decision options.

Targets (QA task list):
 16. single decision option invalid → engine raises (no silent nonsense)
"""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.domain import Decision, DecisionOption
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput
from vencertia.runtime.uncertainty_engine import UncertaintyEngine, compute_option_scores


def test_single_option_decision_raises_value_error():
    """A decision with only one option is invalid → ValueError (fail fast)."""
    decision = Decision(
        id="DEC_SINGLE", decision_question="q", objective_id="OBJ_1",
        project_id="PRJ_1",
        options=[
            DecisionOption(id="only", label="Only", base_utility=0.5,
                           belief_coefficients={}),
        ],
        relevant_belief_ids=[],
    )
    beliefs = []
    engine = DecisionEngine(Settings(), UncertaintyEngine())
    with pytest.raises(ValueError, match="at least two options"):
        engine.evaluate(
            DecisionEngineInput(
                decision=decision,
                beliefs=beliefs,
                risk_aversion=0.25,
                minimum_margin=0.08,
                max_critical_uncertainty=0.45,
                convergence_status="CONVERGED",
            )
        )


def test_compute_option_scores_single_option_returns_one_score():
    """compute_option_scores itself tolerates one option; the engine gate is
    what rejects it (two-layer defense)."""
    decision = Decision(
        id="DEC_SINGLE2", decision_question="q", objective_id="OBJ_1",
        project_id="PRJ_1",
        options=[DecisionOption(id="only", label="Only", base_utility=0.5,
                                belief_coefficients={})],
        relevant_belief_ids=[],
    )
    scores = compute_option_scores(decision, [])
    assert len(scores) == 1


def test_zero_option_decision_is_guarded_at_model_layer():
    """Zero options is rejected by the Decision model itself (pydantic
    min_length=1), so the engine never sees it — fail fast at the boundary."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Decision(
            id="DEC_ZERO", decision_question="q", objective_id="OBJ_1",
            project_id="PRJ_1", options=[], relevant_belief_ids=[],
        )
