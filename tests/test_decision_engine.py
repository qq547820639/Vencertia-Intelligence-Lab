"""DecisionEngine tests: EU, penalties, margin, abstention, type mapping."""

from __future__ import annotations

import pytest

from vencertia.domain import Belief, Decision, DecisionOption
from tests.conftest import make_belief
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput
from vencertia.runtime.uncertainty_engine import UncertaintyEngine


def _belief(bid: str, p: float, alpha: float, beta: float) -> Belief:
    return make_belief(bid, p, alpha, beta)


def _option(oid: str, kind, bu: float, coefs: dict, irr=0.0, opp=0.0) -> DecisionOption:
    return DecisionOption(
        id=oid, label=oid, kind=kind, base_utility=bu,
        belief_coefficients=coefs, irreversible_cost=irr, opportunity_cost=opp,
    )


def _decision(options) -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=options, horizon="short", relevant_belief_ids=["wtp", "problem"],
        status="DRAFT",
    )


def _engine():
    uncertainty = UncertaintyEngine()
    return DecisionEngine(uncertainty_engine=uncertainty)


def test_expected_utility_formula():
    beliefs = [_belief("wtp", 0.8, 8, 2), _belief("problem", 0.6, 6, 4)]
    options = [
        _option("a", "GO", 0.1, {"wtp": 0.5, "problem": 0.5}),
        _option("b", "KILL", 0.2, {"wtp": -0.3, "problem": -0.2}),
    ]
    result = _engine().evaluate(DecisionEngineInput(decision=_decision(options), beliefs=beliefs))
    score_a = next(s for s in result.option_scores if s.option_id == "a")
    # EU(a) = 0.1 + 0.5*0.8 + 0.5*0.6 = 0.8
    assert abs(score_a.expected_utility - 0.8) < 1e-9


def test_abstain_on_insufficient_margin():
    beliefs = [_belief("wtp", 0.5, 1, 1)]
    options = [
        _option("a", "GO", 0.3, {"wtp": 0.5}),
        _option("b", "KILL", 0.3, {"wtp": 0.5}, irr=0.05),
    ]
    result = _engine().evaluate(
        DecisionEngineInput(
            decision=_decision(options), beliefs=beliefs,
            minimum_margin=0.08, max_critical_uncertainty=0.45,
        )
    )
    assert result.status == "ABSTAIN"
    assert result.recommended_option_id is None


def test_go_with_strong_evidence():
    beliefs = [_belief("wtp", 0.9, 36, 4), _belief("problem", 0.85, 30, 5)]
    options = [
        _option("commit", "GO", 0.05, {"wtp": 0.85, "problem": 0.45}, irr=0.4, opp=0.1),
        _option("stop", "KILL", 0.65, {"wtp": -0.3, "problem": -0.2}, irr=0.02),
    ]
    result = _engine().evaluate(DecisionEngineInput(decision=_decision(options), beliefs=beliefs))
    assert result.status == "GO"
    assert result.recommended_option_id == "commit"


def test_kill_mapping():
    beliefs = [_belief("wtp", 0.1, 2, 18), _belief("problem", 0.2, 4, 16)]
    options = [
        _option("commit", "GO", 0.05, {"wtp": 0.85, "problem": 0.45}, irr=0.4, opp=0.1),
        _option("stop", "KILL", 0.65, {"wtp": -0.3, "problem": -0.2}, irr=0.02),
    ]
    result = _engine().evaluate(DecisionEngineInput(decision=_decision(options), beliefs=beliefs))
    assert result.status == "KILL"
    assert result.recommended_option_id == "stop"


def test_pivot_hold_select_conditional_mapping():
    engine = _engine()
    strong = [_belief("wtp", 0.85, 30, 5), _belief("problem", 0.75, 15, 5)]

    pivot_opts = [
        _option("p", "PIVOT", 0.4, {"wtp": 0.3, "problem": 0.4}, irr=0.15, opp=0.05),
        _option("h", "HOLD", 0.2, {"wtp": 0.1, "problem": 0.1}),
    ]
    r = engine.evaluate(DecisionEngineInput(decision=_decision(pivot_opts), beliefs=strong))
    assert r.status == "PIVOT"

    hold_opts = [
        _option("go", "GO", 0.3, {"wtp": 0.6, "problem": 0.4}, irr=0.25, opp=0.1),
        _option("hold", "HOLD", 0.9, {"wtp": 0.2, "problem": 0.1}),
    ]
    weak_wtp = [_belief("wtp", 0.35, 3.5, 6.5), _belief("problem", 0.85, 34, 6)]
    r = engine.evaluate(DecisionEngineInput(decision=_decision(hold_opts), beliefs=weak_wtp))
    assert r.status == "HOLD"

    select_opts = [
        _option("a", "SELECT_OPTION", 0.1, {"wtp": 0.6}),
        _option("b", "SELECT_OPTION", 0.1, {"wtp": 0.4}),
    ]
    r = engine.evaluate(DecisionEngineInput(decision=_decision(select_opts), beliefs=strong))
    assert r.status == "SELECT_OPTION"

    cond_opts = [
        _option("c", "CONDITIONAL_GO", 0.2, {"wtp": 0.7, "problem": 0.4}, irr=0.1, opp=0.05),
        _option("h", "HOLD", 0.15, {"wtp": 0.2, "problem": 0.1}),
    ]
    r = engine.evaluate(DecisionEngineInput(decision=_decision(cond_opts), beliefs=strong))
    assert r.status == "CONDITIONAL_GO"


def test_confidence_formula():
    beliefs = [_belief("wtp", 0.9, 36, 4), _belief("problem", 0.85, 30, 5)]
    options = [
        _option("commit", "GO", 0.05, {"wtp": 0.85, "problem": 0.45}, irr=0.4, opp=0.1),
        _option("stop", "KILL", 0.65, {"wtp": -0.3, "problem": -0.2}, irr=0.02),
    ]
    result = _engine().evaluate(DecisionEngineInput(decision=_decision(options), beliefs=beliefs))
    assert 0 <= result.confidence <= 1


def test_critical_uncertainty_identified():
    beliefs = [_belief("wtp", 0.5, 1, 1), _belief("problem", 0.8, 10, 2.5)]
    options = [
        _option("a", "GO", 0.05, {"wtp": 0.85, "problem": 0.1}, irr=0.4, opp=0.1),
        _option("b", "KILL", 0.65, {"wtp": -0.3, "problem": -0.05}, irr=0.02),
    ]
    result = _engine().evaluate(DecisionEngineInput(decision=_decision(options), beliefs=beliefs))
    assert result.critical_belief_id == "wtp"
    # impact = |0.85 - (-0.3)| * uncertainty(wtp) with unc(wtp)=1.0 at alpha=beta=1
    assert result.critical_uncertainty > 0.45


def test_decision_is_pure_function():
    beliefs = [_belief("wtp", 0.8, 8, 2)]
    options = [
        _option("a", "GO", 0.1, {"wtp": 0.5}),
        _option("b", "KILL", 0.2, {"wtp": -0.3}),
    ]
    decision = _decision(options)
    before = decision.model_dump()
    _engine().evaluate(DecisionEngineInput(decision=decision, beliefs=beliefs))
    assert decision.model_dump() == before  # not mutated
