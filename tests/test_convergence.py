"""ConvergenceEngine tests: 7-state machine."""

from __future__ import annotations

from vencertia.domain import (
    Belief,
    CriticalUncertainty,
    Decision,
    DecisionOption,
    DecisionType,
    Experiment,
)
from vencertia.runtime.convergence_engine import ConvergenceEngine


def _belief(bid, unc) -> Belief:
    return Belief(
        id=bid, claim_id="CLM_" + bid, statement=bid, scope="PROJECT",
        project_id="PRJ_1", posterior=0.5, probability=0.5, alpha=1.0, beta=1.0,
        uncertainty=unc, decision_relevant=True,
    )


def _decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"],
    )


def _critical(bid, impact) -> CriticalUncertainty:
    return CriticalUncertainty(belief_id=bid, statement=bid, impact=impact)


def test_converged_when_no_critical():
    engine = ConvergenceEngine()
    report = engine.check(_decision(), [_belief("wtp", 0.1)], [])
    assert report.status == "CONVERGED"


def test_research_more_with_cheap_research():
    engine = ConvergenceEngine()
    report = engine.check(
        _decision(),
        [_belief("wtp", 0.9)],
        [_critical("wtp", 0.8)],
        experiments=[
            Experiment(id="EXP_INT", name="Interviews", target_belief_ids=["wtp"],
                       expected_information_gain=0.5, decision_impact=0.4, cost=0.3, time=1.0)
        ],
    )
    assert report.status == "RESEARCH_MORE"
    assert report.next_step == "EXP_INT"


def test_experiment_required_when_research_exhausted():
    engine = ConvergenceEngine()
    report = engine.check(
        _decision(),
        [_belief("wtp", 0.9)],
        [_critical("wtp", 0.8)],
        experiments=[
            Experiment(id="EXP_PILOT", name="Paid pilot", target_belief_ids=["wtp"],
                       expected_information_gain=0.95, decision_impact=1.0, cost=2.0, time=10.0)
        ],
    )
    assert report.status == "EXPERIMENT_REQUIRED"


def test_search_exhausted_no_research_no_experiment():
    engine = ConvergenceEngine()
    report = engine.check(
        _decision(),
        [_belief("wtp", 0.9)],
        [_critical("wtp", 0.8)],
        experiments=[],
    )
    assert report.status == "SEARCH_EXHAUSTED"


def test_conditionally_converged_when_impact_within_threshold():
    engine = ConvergenceEngine()
    report = engine.check(
        _decision(),
        [_belief("wtp", 0.2)],
        [_critical("wtp", 0.1)],  # <= 0.45
        experiments=[],
    )
    assert report.status == "CONDITIONALLY_CONVERGED"


def test_execute_when_decision_go():
    engine = ConvergenceEngine()
    report = engine.check(
        _decision(),
        [_belief("wtp", 0.2)],
        [_critical("wtp", 0.1)],
        decision_status=DecisionType.GO,
    )
    assert report.status == "EXECUTE"


def test_converged_for_hold_kill_pivot():
    engine = ConvergenceEngine()
    for status in (DecisionType.HOLD, DecisionType.KILL, DecisionType.PIVOT):
        report = engine.check(
            _decision(), [_belief("wtp", 0.2)], [_critical("wtp", 0.1)],
            decision_status=status,
        )
        assert report.status == "CONVERGED"


def test_conditionally_converged_for_conditional_go():
    engine = ConvergenceEngine()
    report = engine.check(
        _decision(), [_belief("wtp", 0.2)], [_critical("wtp", 0.1)],
        decision_status=DecisionType.CONDITIONAL_GO,
    )
    assert report.status == "CONDITIONALLY_CONVERGED"
