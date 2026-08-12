"""SolveOrchestrator end-to-end tests: solve flow + outcome closed loop."""

from __future__ import annotations

from vencertia.domain import Action, Belief, Decision, DecisionOption, OutcomeType, Project
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest
from tests.conftest import make_belief


def _orchestrator() -> tuple[SolveOrchestrator, InMemoryRepository, EventBus]:
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo, bus=bus, model=MockProvider(), search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    return orchestrator, repo, bus


def test_solve_abstain_with_experiment():
    orchestrator, repo, bus = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_SOLVE", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert result.decision.status == "ABSTAIN"
    assert result.next_experiment is not None
    assert result.critical_uncertainties
    assert result.predictions
    assert result.convergence.status in ("EXPERIMENT_REQUIRED", "RESEARCH_MORE", "SEARCH_EXHAUSTED")


def test_solve_persists_project_and_decision():
    orchestrator, repo, _ = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_SOLVE2", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert repo.get_project("PRJ_SOLVE2") is not None
    assert repo.get_decision(result.decision_id) is not None
    assert repo.get_beliefs("PRJ_SOLVE2")


def test_solve_event_chain():
    orchestrator, repo, _ = _orchestrator()
    orchestrator.solve(
        SolveRequest(project_id="PRJ_SOLVE3", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    events = repo.events_since(0)
    types = [e.event_type for e in events]
    assert "PROJECT_STATE_CHANGED" in types
    assert "DECISION_CREATED" in types
    assert "EVIDENCE_ADDED" in types
    assert "BELIEF_UPDATED" in types
    assert "DECISION_EVALUATED" in types
    assert "PREDICTION_CREATED" in types


def test_outcome_closed_loop():
    orchestrator, repo, bus = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_LOOP", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    decision_id = result.decision_id
    experiment = result.next_experiment.experiment
    repo.save_action(
        Action(id="ACT_1", project_id="PRJ_LOOP", kind="EXPERIMENT",
               description=experiment.action, decision_id=decision_id, experiment_id=experiment.id)
    )
    wtp_before = next(b for b in repo.get_beliefs("PRJ_LOOP") if b.id == "wtp").probability
    recorded = orchestrator.record_outcome(
        "ACT_1", "20 outreach / 6 replies / 3 demos / 0 paid",
        quantitative={"wtp": 0.0, "outreach": 20.0, "replies": 6.0, "demos": 3.0, "paid": 0.0},
        outcome_type=OutcomeType.FAILURE,
    )
    wtp_after = next(b for b in repo.get_beliefs("PRJ_LOOP") if b.id == "wtp").probability
    assert wtp_after < wtp_before  # belief decreased
    assert recorded.decision_update is not None
    assert recorded.outcome.outcome_type == "FAILURE"
    assert recorded.outcome_evidence.authority_level == "PROJECT_EXPERIMENT_RESULT"
    assert len(recorded.predictions_resolved) == 1
    assert recorded.predictions_resolved[0].resolution in ("TRUE", "FALSE", "CANCELLED")


def test_outcome_event_chain_complete():
    orchestrator, repo, _ = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_EVENTS", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    repo.save_action(
        Action(id="ACT_EV", project_id="PRJ_EVENTS", kind="EXPERIMENT",
               description="pilot", decision_id=result.decision_id,
               experiment_id=result.next_experiment.experiment.id)
    )
    orchestrator.record_outcome("ACT_EV", "0 paid", quantitative={"wtp": 0.0}, outcome_type=OutcomeType.FAILURE)
    types = [e.event_type for e in repo.events_since(0)]
    expected = [
        EventType.OUTCOME_RECORDED.value,
        EventType.EVIDENCE_ADDED.value,
        EventType.BELIEF_UPDATED.value,
        EventType.PREDICTION_RESOLVED.value,
        EventType.CALIBRATION_UPDATED.value,
        EventType.DECISION_RE_EVALUATED.value,
    ]
    for event in expected:
        assert event in types, f"missing event {event}"


def test_record_outcome_unknown_action_raises():
    orchestrator, _, _ = _orchestrator()
    from vencertia.repositories.base import EntityNotFoundError

    try:
        orchestrator.record_outcome("ACT_NOPE", "x")
        assert False, "expected EntityNotFoundError"
    except EntityNotFoundError:
        pass


def test_evaluate_decision_updates_decision():
    orchestrator, repo, _ = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_EVAL", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    decision_result, convergence = orchestrator.evaluate_decision(result.decision_id)
    assert decision_result.decision_id == result.decision_id
    stored = repo.get_decision(result.decision_id)
    assert stored.status == "EVALUATED"


class NoExperimentProvider(MockProvider):
    """Provider whose compile output deliberately contains no experiments."""

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        raw = super().generate_structured(task, schema, context)
        raw.pop("experiments", None)
        return raw


def test_solve_abstain_always_carries_next_experiment_without_candidates():
    """Defect-1 regression: ABSTAIN must carry next_experiment even when the
    provider compiles no experiment candidates (ADR-007, provider-independent)."""
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo, bus=bus, model=NoExperimentProvider(),
        search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
    )
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_NOEXP", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert result.decision.status == "ABSTAIN"
    assert result.next_experiment is not None
    # Synthesized experiment targets the decision-critical belief.
    assert result.decision.critical_belief_id in result.next_experiment.experiment.target_belief_ids
    # Semantic consistency: an executable experiment exists -> not SEARCH_EXHAUSTED.
    assert result.convergence.status != "SEARCH_EXHAUSTED"
    # The synthesized experiment is persisted in the repo.
    assert repo.get_experiment(result.next_experiment.experiment.id) is not None


def test_evaluate_decision_persists_evaluated_status_on_fresh_draft():
    """Defect-3 regression: pure evaluate_decision() must persist status=EVALUATED."""
    repo = InMemoryRepository()
    repo.save_project(Project(id="PRJ_EVAL2", user_id="u1", name="x"))
    for belief in (make_belief("wtp", 0.9, 36, 4), make_belief("problem", 0.85, 30, 5)):
        belief.project_id = "PRJ_EVAL2"
        repo.save_belief(belief)
    decision = Decision(
        id="DEC_EVAL2", decision_question="q", objective_id="OBJ_1", project_id="PRJ_EVAL2",
        options=[
            DecisionOption(id="commit", label="Commit", kind="GO", base_utility=0.05,
                           belief_coefficients={"wtp": 0.85, "problem": 0.45},
                           irreversible_cost=0.4, opportunity_cost=0.1),
            DecisionOption(id="stop", label="Stop", kind="KILL", base_utility=0.65,
                           belief_coefficients={"wtp": -0.3, "problem": -0.2},
                           irreversible_cost=0.02),
        ],
        relevant_belief_ids=["wtp", "problem"],
        status="DRAFT",
    )
    repo.save_decision(decision)
    orchestrator = SolveOrchestrator(repo=repo)
    result, _ = orchestrator.evaluate_decision("DEC_EVAL2")
    assert result.status == "GO"
    stored = repo.get_decision("DEC_EVAL2")
    assert stored.status == "EVALUATED"
