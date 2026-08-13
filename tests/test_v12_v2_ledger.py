"""v1.2 V-2 decision ledger acceptance tests."""

from __future__ import annotations

from vencertia.domain import (
    Action,
    DecisionOutcomeRecord,
    DecisionRecord,
    OutcomeType,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest


def _orchestrator():
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    runtime = SolveOrchestrator(
        repo=repo, bus=bus, model=MockProvider(),
        search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
    )
    return runtime, repo


def test_solve_writes_decision_record():
    runtime, repo = _orchestrator()
    result = runtime.solve(
        SolveRequest(
            project_id="PRJ_V2",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    record = repo.get_decision_record(result.decision_id)
    assert record is not None
    assert record.recommendation == result.decision.recommended_option_id
    assert record.model_version == "mock"  # SolveRequest.model_tag default
    assert record.status == "RECOMMENDED"
    if result.decision.status == "ABSTAIN":
        assert record.abstain_reason


def test_record_outcome_backfills_decision_outcome_record():
    runtime, repo = _orchestrator()
    result = runtime.solve(
        SolveRequest(
            project_id="PRJ_V2B",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    record = repo.get_decision_record(result.decision_id)
    assert record is not None

    experiment_id = result.next_experiment.experiment.id if result.next_experiment else None
    repo.save_action(
        Action(
            id="ACT_V2", project_id="PRJ_V2B", kind="EXPERIMENT",
            description="paid pilot", decision_id=result.decision_id,
            experiment_id=experiment_id, status="RUNNING",
        )
    )
    runtime.record_outcome("ACT_V2", "0 paid", outcome_type=OutcomeType.FAILURE)

    outcome_records = repo.list_decision_outcome_records(record.id)
    assert outcome_records
    assert outcome_records[0].regret_estimate is None
    assert outcome_records[0].counterfactual_status == "NOT_IDENTIFIABLE"

    updated = repo.get_decision_record(result.decision_id)
    assert updated.status == "SETTLED"
    assert updated.action_taken == "ACT_V2"


def test_decision_records_persist_across_backends(tmp_db):
    from vencertia.repositories.sqlite import SQLiteRepository

    backends = [InMemoryRepository(), SQLiteRepository(path=tmp_db)]
    for repo in backends:
        repo.save_decision_record(
            DecisionRecord(
                id="DR_1", decision_id="DEC_1", project_id="PRJ_1",
                recommendation="a", status="RECOMMENDED",
            )
        )
        fetched = repo.get_decision_record("DEC_1")
        assert fetched is not None
        assert fetched.id == "DR_1"
        assert [r.id for r in repo.list_decision_records("PRJ_1")] == ["DR_1"]

        repo.save_decision_outcome_record(
            DecisionOutcomeRecord(
                id="OLR_1", decision_record_id="DR_1", outcome_id="OUT_1",
            )
        )
        assert [o.id for o in repo.list_decision_outcome_records("DR_1")] == ["OLR_1"]
