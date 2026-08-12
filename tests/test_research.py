"""Research planning + research stop tests (ADR-011)."""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.domain import (
    Belief,
    CriticalUncertainty,
    Decision,
    DecisionOption,
    ResearchTrace,
)
from vencertia.runtime.research_planner import ResearchPlanner
from vencertia.runtime.research_stop import ResearchStopRule


def _decision() -> Decision:
    return Decision(
        id="DEC_R", decision_question="q", objective_id="OBJ_R", project_id="PRJ_R",
        options=[
            DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
            DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
        ],
        relevant_belief_ids=["wtp"],
    )


def _belief(bid, claim, p=0.5, unc=0.6) -> Belief:
    return Belief(
        id=bid, claim_id=claim, statement=bid, scope="PROJECT", project_id="PRJ_R",
        probability=p, posterior=p, alpha=1.0, beta=1.0, uncertainty=unc,
        decision_relevant=True,
    )


def test_planner_sorts_by_impact():
    planner = ResearchPlanner(settings=Settings())
    beliefs = [_belief("low", "CLM_LOW", unc=0.2), _belief("high", "CLM_HIGH", unc=0.9)]
    criticals = [
        CriticalUncertainty(belief_id="low", statement="low", impact=0.05, uncertainty=0.2),
        CriticalUncertainty(belief_id="high", statement="high", impact=0.6, uncertainty=0.9),
    ]
    plan = planner.plan(_decision(), beliefs, criticals, None)
    assert plan.questions
    assert plan.questions[0].target_claim_ids == ["CLM_HIGH"]
    assert plan.questions[0].expected_decision_impact == pytest.approx(0.6)


def test_planner_empty_without_criticals():
    planner = ResearchPlanner(settings=Settings())
    plan = planner.plan(_decision(), [], [], None)
    assert plan.questions == []


def test_stop_rule_continues_when_marginal_value_high():
    rule = ResearchStopRule(settings=Settings(research_stop_marginal_value=0.02))
    before = [_belief("wtp", "CLM_WTP", p=0.4)]
    after = [_belief("wtp", "CLM_WTP", p=0.6)]
    traces = [
        ResearchTrace(
            id="RT_1", decision_id="DEC_R", question_id="RQ_1", results_retrieved=10,
            duplicate_dropped=1, queries_executed=2, new_evidence_ids=["E_1"],
        )
    ]
    report = rule.evaluate(traces, before, after, ["CLM_WTP"], round_no=1)
    assert report.status == "RESEARCH_MORE"


def test_stop_rule_exhausted_on_low_delta_high_dup():
    rule = ResearchStopRule(settings=Settings(research_stop_marginal_value=0.02))
    before = [_belief("wtp", "CLM_WTP", p=0.5)]
    after = [_belief("wtp", "CLM_WTP", p=0.501)]
    traces = [
        ResearchTrace(
            id="RT_1", decision_id="DEC_R", question_id="RQ_1", results_retrieved=10,
            duplicate_dropped=8, queries_executed=2, new_evidence_ids=[],
        )
    ]
    report = rule.evaluate(traces, before, after, ["CLM_WTP"], round_no=2)
    assert report.status == "SEARCH_EXHAUSTED"
    assert "duplicate" in report.reason


def test_stop_rule_experiment_required_when_no_new_evidence():
    rule = ResearchStopRule(settings=Settings())
    before = [_belief("wtp", "CLM_WTP", p=0.5)]
    after = [_belief("wtp", "CLM_WTP", p=0.5)]
    traces = [
        ResearchTrace(
            id="RT_1", decision_id="DEC_R", question_id="RQ_1", results_retrieved=5,
            duplicate_dropped=1, queries_executed=1, new_evidence_ids=["E_1"],
        ),
        ResearchTrace(
            id="RT_2", decision_id="DEC_R", question_id="RQ_1", results_retrieved=5,
            duplicate_dropped=2, queries_executed=1, new_evidence_ids=[],
        ),
    ]
    report = rule.evaluate(traces, before, after, ["CLM_WTP"], round_no=2)
    assert report.status == "EXPERIMENT_REQUIRED"


def test_stop_rule_signal_set_complete():
    rule = ResearchStopRule(settings=Settings())
    before = [_belief("wtp", "CLM_WTP", p=0.5)]
    after = [_belief("wtp", "CLM_WTP", p=0.52)]
    traces = [
        ResearchTrace(
            id="RT_1", decision_id="DEC_R", question_id="RQ_1", results_retrieved=6,
            duplicate_dropped=2, queries_executed=2, new_evidence_ids=["E_1"],
        )
    ]
    report = rule.evaluate(traces, before, after, ["CLM_WTP"], round_no=1)
    for key in (
        "marginal_value",
        "belief_delta",
        "duplicate_rate",
        "source_quality",
        "source_diversity",
        "claim_coverage",
        "search_cost",
        "decision_change_prob",
    ):
        assert key in report.signals
