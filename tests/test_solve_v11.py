"""v1.1 end-to-end solve tests: research → binding → belief → sensitivity.

These exercise the new SolveResultV11 fields and the closed research loop.
"""

from __future__ import annotations

from vencertia.domain import BeliefUpdateRecord
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, SolveResultV11


def _orchestrator() -> tuple[SolveOrchestrator, InMemoryRepository]:
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo, bus=bus, model=MockProvider(), search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    return orchestrator, repo


def test_solve_v11_binds_evidence():
    orchestrator, repo = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V11", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert isinstance(result, SolveResultV11)
    bindings = repo.list_bindings()
    assert len(bindings) > 0
    bound = [b for b in bindings if b.claim_id is not None]
    assert len(bound) > 0
    # Evidence used must match belief evidence chains.
    beliefs = repo.get_beliefs("PRJ_V11")
    evidence_ids = set(result.evidence_used)
    for belief in beliefs:
        for eid in belief.supporting_evidence_ids + belief.contradicting_evidence_ids:
            assert eid in evidence_ids


def test_solve_v11_research_traces_and_stop():
    orchestrator, repo = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V11B", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert result.research_performed  # non-empty
    assert result.stop_condition in ("RESEARCH_MORE", "SEARCH_EXHAUSTED", "EXPERIMENT_REQUIRED")
    assert repo.list_research_traces(result.decision_id)


def test_solve_v11_belief_snapshot_has_posterior_version():
    orchestrator, _ = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V11C", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert result.belief_snapshot
    for row in result.belief_snapshot:
        assert row["posterior_version"] >= 1


def test_solve_v11_persists_decision_trace_and_sensitivity():
    orchestrator, repo = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V11D", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert result.why is not None
    assert repo.get_decision_trace(result.decision_id) is not None
    assert repo.get_decision_sensitivity(result.decision_id) is not None
    assert result.robustness in ("STRONG_DECISION", "FRAGILE_DECISION")


def test_solve_v11_belief_update_records_persisted():
    orchestrator, repo = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V11E", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    records = repo.list_belief_update_records("wtp")
    assert records
    record = records[-1]
    assert isinstance(record, BeliefUpdateRecord)
    assert record.policy_version == "1.1"
    assert record.evidence_used
    assert record.new_probability != record.old_probability or record.effective_weight >= 0


def test_solve_v11_emits_research_and_binding_events():
    orchestrator, repo = _orchestrator()
    orchestrator.solve(
        SolveRequest(project_id="PRJ_V11F", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    types = [e.event_type for e in repo.events_since(0)]
    assert EventType.RESEARCH_PLANNED.value in types
    assert EventType.RESEARCH_COMPLETED.value in types
    assert EventType.EVIDENCE_BOUND_TO_CLAIM.value in types
    assert EventType.DECISION_SENSITIVITY_COMPUTED.value in types


def test_calibrated_confidence_uncertain_uncalibrated():
    orchestrator, _ = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V11G", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert result.confidence_calibrated is not None
    assert result.confidence_calibrated.status == "UNCALIBRATED"
    assert result.confidence_calibrated.calibrated is None


def test_solve_v11_evidence_rejected_field_present():
    orchestrator, _ = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V11H", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    assert isinstance(result.evidence_rejected, list)
