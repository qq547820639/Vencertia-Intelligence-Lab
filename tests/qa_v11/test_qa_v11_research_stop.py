"""QA adversarial tests — Research Stop + SEARCH_EXHAUSTED→EXPERIMENT (P0, ADR-011).

Verifies the stop rule is signal-based (not a rubber stamp), and that in the
full solve loop SEARCH_EXHAUSTED genuinely converts to EXPERIMENT_REQUIRED with
a non-empty next experiment.
"""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import Belief, CriticalUncertainty, Decision, DecisionOption, ResearchTrace
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest
from vencertia.runtime.research_planner import ResearchPlanner
from vencertia.runtime.research_stop import ResearchStopRule


def _decision() -> Decision:
    return Decision(
        id="DEC_QA_R", decision_question="q", objective_id="OBJ_QA_R", project_id="PRJ_QA_R",
        options=[
            DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
            DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
        ],
        relevant_belief_ids=["wtp"],
    )


def _belief(bid, claim, p=0.5, unc=0.6) -> Belief:
    return Belief(
        id=bid, claim_id=claim, statement=bid, scope="PROJECT", project_id="PRJ_QA_R",
        probability=p, posterior=p, alpha=1.0, beta=1.0, uncertainty=unc,
        decision_relevant=True,
    )


def _trace(tid, retrieved=5, dropped=0, new_ids=None, queries=1) -> ResearchTrace:
    return ResearchTrace(
        id=tid, decision_id="DEC_QA_R", question_id="RQ_1",
        results_retrieved=retrieved, duplicate_dropped=dropped,
        new_evidence_ids=new_ids or [], queries_executed=queries,
        provider="mock_search", model="mock",
    )


def test_qa_stop_rule_seach_exhausted_on_duplicate_loop():
    """Consecutive duplicate/low-marginal rounds -> SEARCH_EXHAUSTED."""
    rule = ResearchStopRule(settings=Settings(research_stop_marginal_value=0.02))
    before = [_belief("wtp", "CLM_WTP", p=0.5)]
    after = [_belief("wtp", "CLM_WTP", p=0.501)]
    traces = [_trace("RT_1", retrieved=10, dropped=8, new_ids=["E_1"])]
    report = rule.evaluate(traces, before, after, ["CLM_WTP"], round_no=2)
    assert report.status == "SEARCH_EXHAUSTED"
    assert report.signals["belief_delta"] < 0.02
    assert report.signals["duplicate_rate"] > 0.5


def test_qa_stop_rule_experiment_required_when_no_new_evidence():
    """Desktop research yields nothing new -> EXPERIMENT_REQUIRED."""
    rule = ResearchStopRule(settings=Settings())
    before = [_belief("wtp", "CLM_WTP", p=0.5)]
    after = [_belief("wtp", "CLM_WTP", p=0.5)]
    traces = [
        _trace("RT_1", retrieved=5, dropped=1, new_ids=["E_1"]),
        _trace("RT_2", retrieved=5, dropped=2, new_ids=[]),
    ]
    report = rule.evaluate(traces, before, after, ["CLM_WTP"], round_no=2)
    assert report.status == "EXPERIMENT_REQUIRED"


def test_qa_stop_rule_continues_when_evidence_moves_beliefs():
    rule = ResearchStopRule(settings=Settings(research_stop_marginal_value=0.02))
    before = [_belief("wtp", "CLM_WTP", p=0.4)]
    after = [_belief("wtp", "CLM_WTP", p=0.6)]
    traces = [_trace("RT_1", retrieved=10, dropped=1, new_ids=["E_1", "E_2"])]
    report = rule.evaluate(traces, before, after, ["CLM_WTP"], round_no=1)
    assert report.status == "RESEARCH_MORE"


def test_qa_planner_generates_decision_critical_questions():
    """ResearchPlanner targets the highest-impact critical uncertainty."""
    planner = ResearchPlanner(settings=Settings())
    beliefs = [_belief("wtp", "CLM_WTP", unc=0.9)]
    criticals = [CriticalUncertainty(belief_id="wtp", statement="wtp", impact=0.8, uncertainty=0.9)]
    plan = planner.plan(_decision(), beliefs, criticals, None)
    assert plan.questions
    q = plan.questions[0]
    assert q.target_claim_ids == ["CLM_WTP"]
    assert q.search_queries  # actionable queries, not empty
    assert q.stop_condition  # explicit stop condition


def test_qa_solve_seach_exhausted_converts_to_experiment_required():
    """Full loop: SEARCH_EXHAUSTED -> convergence EXPERIMENT_REQUIRED + next experiment."""
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
        settings=Settings(research_max_rounds=1),  # force SEARCH_EXHAUSTED after round 1
    )
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_QA_STOP", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert result.stop_condition == "SEARCH_EXHAUSTED"
    assert result.convergence.status == "EXPERIMENT_REQUIRED"
    # SEARCH_EXHAUSTED must still yield an executable experiment (ADR-007).
    assert result.next_experiment is not None
    assert result.next_experiment.experiment.success_criteria
    assert result.next_experiment.experiment.failure_criteria
