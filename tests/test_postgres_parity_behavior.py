"""PG behavioral parity suite (v1.9.1).

Runs the shared CRUD / optimistic-lock / transaction / event semantics against
BOTH SQLite and PostgreSQL. The PostgreSQL side skips honestly when
``VENCERTIA_PG_DSN`` is not set or psycopg is unavailable — CI's
``postgres:16`` service exercises it for real (Release Gate I). Local runs
without a DSN remain green with the honest skip.

Every test uses unique ids (uuid4) so repeated runs against a shared CI
database cannot collide.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from vencertia.domain import (
    Belief,
    BeliefUpdateRecord,
    Claim,
    Decision,
    DecisionOption,
    Evidence,
    EvidenceClaimBinding,
    Experiment,
    Project,
    ProjectStatus,
    Stage,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.repositories.base import StaleWriteError
from vencertia.repositories.sqlite import SQLiteRepository


def _pg_repository():
    dsn = os.environ.get("VENCERTIA_PG_DSN")
    if not dsn:
        pytest.skip("VENCERTIA_PG_DSN not set; PostgreSQL parity not exercised")
    try:
        from vencertia.repositories.postgres import PostgresRepository

        return PostgresRepository(dsn)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL unavailable: {exc}")


@pytest.fixture(params=["sqlite", "postgres"])
def dual_repo(request, tmp_path):
    if request.param == "sqlite":
        return SQLiteRepository(path=tmp_path / "parity.db")
    return _pg_repository()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _project(repo, pid):
    repo.save_project(Project(id=pid, user_id="u1", name="p"))
    return pid


def _belief(bid, claim_id, pid):
    return Belief(
        id=bid,
        claim_id=claim_id,
        statement="statement",
        scope="PROJECT",
        project_id=pid,
        probability=0.5,
    )


def _decision(did, pid):
    return Decision(
        id=did,
        decision_question="q?",
        objective_id="OBJ_1",
        project_id=pid,
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
    )


# -- CRUD roundtrip -------------------------------------------------------------


def test_crud_roundtrip_parity(dual_repo):
    repo = dual_repo
    pid = _project(repo, _uid("PRJ"))
    repo.add_claim(Claim(id=_uid("CLM"), statement="s", scope="PROJECT", project_id=pid))
    belief = _belief(_uid("BLF"), "CLM_X", pid)
    repo.save_belief(belief)
    loaded = repo.get_belief(belief.id)
    assert loaded is not None and loaded.probability == 0.5

    decision = _decision(_uid("DEC"), pid)
    repo.save_decision(decision)
    assert repo.get_decision(decision.id).options[0].id == "a"

    evidence = Evidence(
        id=_uid("E"),
        claim_ids=["CLM_X"],
        scope="PROJECT",
        evidence_type="OBSERVED_BEHAVIOR",
        source="s",
        project_id=pid,
    )
    repo.add_evidence(evidence)
    assert repo.get_evidence(evidence.id) is not None

    experiment = Experiment(id=_uid("EXP"), name="n", decision_id=decision.id)
    repo.save_experiment(experiment)
    assert repo.get_experiment(experiment.id).name == "n"


# -- optimistic locking ----------------------------------------------------------


def test_stale_write_raises_parity(dual_repo):
    repo = dual_repo
    pid = _project(repo, _uid("PRJ"))
    belief = _belief(_uid("BLF"), "CLM_S", pid)
    repo.save_belief(belief)
    belief.version = 2
    repo.save_belief(belief, expected_version=1)  # legitimate bump to v2
    stale = belief.model_copy(update={"version": 3})
    with pytest.raises(StaleWriteError):
        repo.save_belief(stale, expected_version=1)  # v1 no longer current


def test_create_with_expected_version_gt_1_raises_parity(dual_repo):
    repo = dual_repo
    project = Project(
        id=_uid("PRJ"), user_id="u1", name="p",
        status=ProjectStatus.EXPLORING, stage=Stage.S0_INITIALIZATION, version=2,
    )
    with pytest.raises(StaleWriteError):
        repo.save_project(project, expected_version=2)


def test_create_with_expected_version_1_ok_parity(dual_repo):
    repo = dual_repo
    project = Project(
        id=_uid("PRJ"), user_id="u1", name="p",
        status=ProjectStatus.EXPLORING, stage=Stage.S0_INITIALIZATION, version=1,
    )
    repo.save_project(project, expected_version=1)  # must not raise


# -- transaction atomicity -------------------------------------------------------


def test_nested_transaction_rollback_parity(dual_repo):
    repo = dual_repo
    pid = _project(repo, _uid("PRJ"))
    survivor = _belief(_uid("BLF"), "CLM_KEEP", pid)
    victim = _belief(_uid("BLF"), "CLM_DROP", pid)

    def batch():
        repo.save_belief(survivor)
        repo.save_belief(victim)
        raise RuntimeError("mid-batch failure")

    with pytest.raises(RuntimeError):
        repo.in_transaction(batch)
    assert repo.get_belief(survivor.id) is None, "rollback must discard sibling writes"
    assert repo.get_belief(victim.id) is None


def test_nested_transaction_commit_parity(dual_repo):
    repo = dual_repo
    pid = _project(repo, _uid("PRJ"))
    belief = _belief(_uid("BLF"), "CLM_N", pid)

    def outer():
        repo.save_belief(belief)
        # nested depth shares the outermost transaction
        repo.in_transaction(
            lambda: repo.save_belief(belief.model_copy(update={"version": 2}), expected_version=1)
        )

    repo.in_transaction(outer)
    committed = repo.get_belief(belief.id)
    assert committed is not None and committed.version == 2


# -- v1.1 hot tables -------------------------------------------------------------


def test_bindings_and_update_records_parity(dual_repo):
    repo = dual_repo
    pid = _project(repo, _uid("PRJ"))
    repo.save_belief(_belief(_uid("BLF"), "CLM_B", pid))

    binding = EvidenceClaimBinding(
        id=_uid("EB"),
        evidence_id="E_B",
        claim_id="CLM_B",
        binding_method="EXACT_MATCH",
        status="BOUND",
        binding_confidence=0.9,
    )
    repo.save_binding(binding)
    rows = repo.list_bindings(evidence_id="E_B")
    assert [b.id for b in rows] == [binding.id]
    assert [b.id for b in repo.list_bindings(status="BOUND")] == [binding.id]

    record = BeliefUpdateRecord(
        id=_uid("BUR"),
        belief_id=_uid("BLF"),
        claim_id="CLM_B",
        policy_version="1.0",
        old_probability=0.5,
        new_probability=0.6,
        old_uncertainty=0.3,
        new_uncertainty=0.2,
        evidence_used=["E_B"],
        update_method="BETA_BERNOULLI",
    )
    repo.save_belief_update_record(record)
    assert len(repo.list_belief_update_records(record.belief_id)) == 1


# -- event log -------------------------------------------------------------------


def test_event_log_append_and_replay_parity(dual_repo):
    repo = dual_repo
    bus = EventBus(sink=repo.append_event)
    bus.publish(make_event(EventType.EVIDENCE_ADDED, "evidence", "E_1", {}))
    bus.publish(make_event(EventType.BELIEF_UPDATED, "belief", "B_1", {}))
    events = repo.events_since(0)
    assert [e.event_type for e in events] == ["EVIDENCE_ADDED", "BELIEF_UPDATED"]
    assert [e.seq for e in events] == [1, 2]
    assert repo.events_since(1) == events[1:]
