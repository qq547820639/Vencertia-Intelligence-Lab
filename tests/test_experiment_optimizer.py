"""ExperimentOptimizer tests: scoring formula, separation, propose contract."""

from __future__ import annotations

from vencertia.domain import Belief, Decision, DecisionOption, Experiment
from vencertia.runtime.experiment_optimizer import (
    ExperimentOptimizer,
    ExperimentProposalInput,
)


def _belief(bid, unc, weight=1.0) -> Belief:
    return Belief(
        id=bid, claim_id="CLM_" + bid, statement=bid, scope="PROJECT",
        project_id="PRJ_1", posterior=0.5, probability=0.5, alpha=1.0, beta=1.0,
        uncertainty=unc, decision_weight=weight, decision_relevant=True,
    )


def _exp(eid, targets, eig, impact, cost=1.0, time=1.0, rev=1.0) -> Experiment:
    return Experiment(
        id=eid, name=eid, target_belief_ids=targets,
        expected_information_gain=eig, decision_impact=impact,
        cost=cost, time=time, reversibility=rev,
    )


def _decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp", "problem"],
    )


def test_critical_belief_is_prioritized():
    beliefs = [_belief("wtp", 0.8), _belief("problem", 0.8)]
    experiments = [
        _exp("e_problem", ["problem"], 0.9, 0.9),
        _exp("e_wtp", ["wtp"], 0.7, 0.8),
    ]
    ranked = ExperimentOptimizer().rank(experiments, beliefs, critical_belief_id="wtp")
    assert ranked[0].experiment.id == "e_wtp"


def test_time_penalty():
    beliefs = [_belief("wtp", 0.8)]
    fast = _exp("fast", ["wtp"], 0.9, 1.0, cost=1.0, time=2.0)
    slow = _exp("slow", ["wtp"], 0.9, 1.0, cost=1.0, time=20.0)
    ranked = ExperimentOptimizer().rank([fast, slow], beliefs)
    assert ranked[0].experiment.id == "fast"


def test_cost_penalty():
    beliefs = [_belief("wtp", 0.8)]
    cheap = _exp("cheap", ["wtp"], 0.8, 1.0, cost=0.5, time=3.0)
    dear = _exp("dear", ["wtp"], 0.8, 1.0, cost=5.0, time=3.0)
    ranked = ExperimentOptimizer().rank([cheap, dear], beliefs)
    assert ranked[0].experiment.id == "cheap"


def test_uncertainty_floor():
    beliefs = [_belief("wtp", 0.01)]
    exp = _exp("e", ["wtp"], 0.5, 0.5)
    ranked = ExperimentOptimizer().rank([exp], beliefs)
    # uncertainty floor 0.05 keeps score > 0
    assert ranked[0].priority_score > 0


def test_propose_contract_abstain_with_experiment():
    beliefs = [_belief("wtp", 1.0)]
    candidates = [_exp("pilot", ["wtp"], 0.95, 1.0)]
    proposal = ExperimentOptimizer().propose(
        ExperimentProposalInput(
            decision=_decision(), beliefs=beliefs,
            critical_belief_id="wtp", candidates=candidates, max_results=5,
        )
    )
    assert proposal.decision_insufficient is True
    assert len(proposal.ranked) == 1
    assert proposal.ranked[0].experiment.id == "pilot"


def test_experiments_not_in_decision_scoring():
    """Experiments must never be scored as decision options (ADR-003)."""
    from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput

    beliefs = [_belief("wtp", 0.8)]
    decision = _decision()
    result = DecisionEngine().evaluate(
        DecisionEngineInput(decision=decision, beliefs=beliefs)
    )
    option_ids = {s.option_id for s in result.option_scores}
    assert "pilot" not in option_ids
    assert option_ids == {"a", "b"}
