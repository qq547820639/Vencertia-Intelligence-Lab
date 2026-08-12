"""QA adversarial tests — Requirements 10 & 13: real SQLite persistence,
optimistic locking, and event-log replay (rebuild evidence chain from event_log).
"""

from __future__ import annotations

import sqlite3

import pytest

from vencertia.domain import (
    Action,
    Belief,
    Decision,
    DecisionOption,
    OutcomeType,
    Project,
    Scope,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.mock import MockProvider, MockSearchProvider, MockRetrievalProvider
from vencertia.repositories.base import StaleWriteError
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest


def test_sqlite_persists_beliefs_and_decision_across_reopen(tmp_path) -> None:
    db_path = tmp_path / "persist.db"
    r1 = SQLiteRepository(path=db_path)
    r1.save_project(Project(id="PRJ_P", user_id="u1", name="p"))
    r1.save_belief(
        Belief(id="wtp", claim_id="CLM_WTP", statement="pay", scope=Scope.PROJECT,
               project_id="PRJ_P", posterior=0.6, probability=0.6, alpha=4, beta=2,
               decision_relevant=True)
    )
    r1.save_decision(
        Decision(id="DEC_P", decision_question="q", objective_id="OBJ_1", project_id="PRJ_P",
                 options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")])
    )
    del r1  # close handle

    r2 = SQLiteRepository(path=db_path)  # reopen same file
    assert r2.get_project("PRJ_P") is not None
    belief = r2.get_belief("wtp")
    assert belief is not None and belief.probability == 0.6
    assert r2.get_decision("DEC_P").options[0].id == "a"


def test_stale_write_on_decision_raises(tmp_path) -> None:
    repo = SQLiteRepository(path=":memory:")
    decision = Decision(
        id="DEC_S", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
    )
    repo.save_decision(decision)
    reader1 = repo.get_decision("DEC_S")
    reader2 = repo.get_decision("DEC_S")
    reader1.status = "EVALUATED"
    reader1.version += 1
    repo.save_decision(reader1, expected_version=1)
    reader2.status = "EXECUTED"
    reader2.version += 1
    with pytest.raises(StaleWriteError):
        repo.save_decision(reader2, expected_version=1)


def test_event_log_replay_rebuilds_evidence_chain(tmp_path) -> None:
    """Requirement 13: event_log table can replay EVIDENCE_ADDED events to
    reconstruct the evidence chain (what was added and in what order)."""
    db_path = tmp_path / "events.db"
    repo = SQLiteRepository(path=db_path)
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    orchestrator.solve(
        SolveRequest(project_id="PRJ_EV", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )

    # Replay from the raw event_log table.
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT seq, event_type, entity_id, payload FROM event_log ORDER BY seq"
    ).fetchall()
    conn.close()
    assert rows, "event_log table must contain events"

    evidence_event_ids = [
        r["entity_id"] for r in rows if r["event_type"] == EventType.EVIDENCE_ADDED.value
    ] if rows else []
    # Compare against the canonical evidence store.
    stored_ids = {e.id for e in repo.list_evidence()}
    assert set(evidence_event_ids) == stored_ids
    assert stored_ids, "solve must ingest at least one evidence record"


def test_event_log_events_are_sequenced(tmp_path) -> None:
    repo = SQLiteRepository(path=":memory:")
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(repo=repo, bus=bus, model=MockProvider())
    orchestrator.solve(
        SolveRequest(project_id="PRJ_SEQ", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    events = repo.events_since(0)
    seqs = [e.seq for e in events]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    # Replay supports incremental consumption.
    tail = repo.events_since(events[0].seq or 0)
    assert tail[0].entity_id == events[1].entity_id
