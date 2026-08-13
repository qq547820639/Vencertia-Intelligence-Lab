"""v1.9 round 2 — tech-debt cleanup regression tests.

Covers:
- lifecycle event emission (ACTION_CREATED / EXPERIMENT_STARTED /
  EXPERIMENT_RESOLVED / CONTEXT_INVALIDATED)
- L1 runtime JSON-Schema validation (schema-invalid cases are rejected, not run)
- claim_binding authored-case scope fail-loud
- repository close() lifecycle (SQLite)
- make_release coverage-artifact file filter
- UI progressive disclosure (展开完整模型)
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.domain import Experiment
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime import SolveOrchestrator, default_engine_bundle


@pytest.fixture
def client_and_repo():
    """A fully-wired in-memory app whose repository is returned for inspection."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo,
        policy=engines.evidence_policy,
        engines=engines,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
        bus=bus,
        settings=settings,
    )
    return TestClient(create_app(settings, repo, runtime)), repo


def _event_types(repo) -> set[str]:
    return {e.event_type for e in repo.events_since(0)}


def _seed_experiment(repo) -> None:
    from vencertia.domain import Decision, DecisionOption, Project, ProjectStatus, Stage

    repo.save_project(
        Project(id="PRJ_EVT", user_id="u1", name="p", status=ProjectStatus.EXPLORING,
                stage=Stage.S0_INITIALIZATION)
    )
    repo.save_decision(
        Decision(id="DEC_EVT", decision_question="q", objective_id="OBJ_1",
                 project_id="PRJ_EVT",
                 options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")])
    )
    repo.save_experiment(
        Experiment(
            id="EXP_EVT", name="pilot", hypothesis="h",
            decision_id="DEC_EVT", action="run a paid pilot",
            success_criteria=">= 2 paid", failure_criteria="0 paid",
            ambiguity_criteria="1 paid", cost=1.0,
        )
    )


# -- lifecycle events ------------------------------------------------------------


def test_solve_emits_context_invalidated(client_and_repo):
    client, repo = client_and_repo
    r = client.post(
        "/v1/solve?view=summary",
        json={"project_id": "PRJ_CTX", "problem_text": "是否投入 6 周做 MVP？"},
    )
    assert r.status_code == 200
    assert EventType.CONTEXT_INVALIDATED in _event_types(repo)


def test_experiment_resolve_emits_lifecycle_events(client_and_repo):
    client, repo = client_and_repo
    _seed_experiment(repo)
    r = client.post(
        "/v1/experiments/EXP_EVT/resolve",
        json={"result": "3 pilots paid", "outcome_type": "SUCCESS"},
    )
    assert r.status_code == 200, r.text
    types = _event_types(repo)
    assert EventType.ACTION_CREATED in types
    assert EventType.EXPERIMENT_STARTED in types
    assert EventType.EXPERIMENT_RESOLVED in types


# -- L1 schema validation --------------------------------------------------------


def test_l1_schema_invalid_case_is_rejected(tmp_path):
    from vencertia.benchmark.l1 import L1Runner

    lines = [
        json.dumps(
            {
                "id": "l1-bad",
                "leakage_audit_passed": True,
                # missing decision_time -> schema violation
                "information_available_at_t0": {"decision": {}},
            }
        ),
    ]
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    report = L1Runner().run(path)
    assert report.rejected, "schema-invalid case must be rejected"
    assert any("schema-invalid" in r for r in report.rejected)


def test_l1_shipped_cases_all_pass_schema(project_root):
    from vencertia.benchmark.l1 import L1Runner

    path = project_root / "data" / "benchmarks" / "l1_cases.jsonl"
    report = L1Runner().run(path)
    assert not any("schema-invalid" in r for r in report.rejected), report.rejected


# -- claim binding scope fail-loud ------------------------------------------------


def test_claim_binding_unknown_scope_raises():
    from vencertia.benchmark.claim_binding import _scope

    with pytest.raises(ValueError):
        _scope("NOT_A_SCOPE")


# -- repository close() -----------------------------------------------------------


def test_sqlite_repository_close_is_idempotent(tmp_path):
    repo = SQLiteRepository(path=tmp_path / "close.db")
    repo.close()
    repo.close()  # second close must not raise
    with pytest.raises(sqlite3.ProgrammingError):
        repo.conn.execute("SELECT 1")


def test_sqlite_repository_context_manager(tmp_path):
    from vencertia.domain import Project, ProjectStatus, Stage

    with SQLiteRepository(path=tmp_path / "ctx.db") as repo:
        repo.save_project(
            Project(id="PRJ_CM", user_id="u1", name="p", status=ProjectStatus.EXPLORING,
                    stage=Stage.S0_INITIALIZATION)
        )
    # reopening proves the data committed before close
    reopened = SQLiteRepository(path=tmp_path / "ctx.db")
    try:
        assert reopened.get_project("PRJ_CM") is not None
    finally:
        reopened.close()


# -- make_release filter ----------------------------------------------------------


def test_make_release_skips_coverage_artifacts():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "make_release",
        pathlib.Path(__file__).resolve().parents[1] / "scripts" / "make_release.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._should_skip_file(".coverage")
    assert module._should_skip_file("coverage.xml")
    assert module._should_skip_file("vencertia.db")
    assert not module._should_skip_file("api.py")


# -- UI progressive disclosure ----------------------------------------------------


def test_ui_renders_full_model_disclosure(api_client):
    js = api_client.get("/static/app.js")
    assert js.status_code == 200
    assert "展开完整模型" in js.text
