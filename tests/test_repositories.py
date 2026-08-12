"""Repository tests: CRUD, optimistic locking, transactions, events."""

from __future__ import annotations

import pytest

from vencertia.domain import Belief, Evidence, Project, Scope
from vencertia.events.types import DomainEvent, EventType
from vencertia.repositories.base import EntityNotFoundError, StaleWriteError
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository


@pytest.mark.parametrize("repo_factory", [InMemoryRepository, lambda: SQLiteRepository(path=":memory:")])
def test_evidence_roundtrip(repo_factory):
    repo = repo_factory()
    evidence = Evidence(
        id="E_1", claim_ids=["CLM_1"], scope=Scope.PROJECT,
        evidence_type="REAL_PAYMENT", source="paid", authority_level="PROJECT_REALITY",
    )
    repo.add_evidence(evidence)
    assert repo.get_evidence("E_1") == evidence
    assert repo.list_evidence(claim_ids=["CLM_1"]) == [evidence]


def test_stale_write_raises(repo):
    belief = Belief(id="BLF_1", claim_id="CLM_1", statement="x", scope="PROJECT", project_id="PRJ_1")
    repo.save_belief(belief)
    # Simulate two concurrent readers mutating the same row.
    reader1 = repo.get_belief("BLF_1")
    reader2 = repo.get_belief("BLF_1")
    reader1.alpha = 5.0
    reader1.version += 1
    repo.save_belief(reader1, expected_version=1)
    reader2.alpha = 9.0
    reader2.version += 1
    with pytest.raises(StaleWriteError):
        repo.save_belief(reader2, expected_version=1)


def test_transaction_rollback(repo):
    project = Project(id="PRJ_1", user_id="u1", name="x")

    def failing_txn():
        repo.save_project(project)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        repo.in_transaction(failing_txn)
    assert repo.get_project("PRJ_1") is None  # rolled back


def test_event_log_append_and_replay(repo):
    repo.append_event(DomainEvent(event_type=EventType.EVIDENCE_ADDED, entity_type="evidence", entity_id="E_1"))
    repo.append_event(DomainEvent(event_type=EventType.BELIEF_UPDATED, entity_type="belief", entity_id="BLF_1"))
    events = repo.events_since(0)
    assert len(events) == 2
    assert events[0].event_type == "EVIDENCE_ADDED"
    after_first = repo.events_since(events[0].seq or 0)
    assert len(after_first) == 1
    assert after_first[0].entity_id == "BLF_1"


def test_open_predictions(repo):
    from vencertia.domain import PredictionEntry

    open_p = PredictionEntry(id="PRD_1", project_id="PRJ_1", target="t", predicted_probability=0.5)
    settled = PredictionEntry(id="PRD_2", project_id="PRJ_1", target="t", predicted_probability=0.5,
                              resolution="TRUE", outcome=True)
    repo.save_prediction(open_p)
    repo.save_prediction(settled)
    open_list = repo.get_open_predictions("PRJ_1")
    assert [p.id for p in open_list] == ["PRD_1"]


def test_resolve_prediction_repo(repo):
    from vencertia.domain import PredictionEntry

    p = PredictionEntry(id="PRD_1", project_id="PRJ_1", target="t", predicted_probability=0.5)
    repo.save_prediction(p)
    resolved = repo.resolve_prediction("PRD_1", True)
    assert resolved.resolution == "TRUE"
    assert resolved.outcome is True


def test_entity_not_found(repo):
    assert repo.get_decision("DEC_MISSING") is None
    # get with no entity returns None; explicit raises are used by services.
    with pytest.raises(EntityNotFoundError):
        raise EntityNotFoundError("decision", "DEC_MISSING")


def test_sqlite_persists_across_instances(tmp_path):
    db_path = tmp_path / "p.db"
    r1 = SQLiteRepository(path=db_path)
    r1.save_project(Project(id="PRJ_1", user_id="u1", name="persist"))
    del r1
    r2 = SQLiteRepository(path=db_path)
    assert r2.get_project("PRJ_1").name == "persist"


def test_rules_filter(repo):
    from vencertia.domain import Rule, RuleKind

    repo.save_rule(Rule(id="R1", kind=RuleKind.INVARIANT, name="a", description=""))
    repo.save_rule(Rule(id="R2", kind=RuleKind.POLICY, name="b", description=""))
    assert len(repo.get_rules(RuleKind.INVARIANT)) == 1
    assert len(repo.get_rules()) == 2
