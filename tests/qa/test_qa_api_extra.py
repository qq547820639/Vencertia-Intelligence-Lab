"""QA adversarial tests — Requirement 11: API 13+ endpoints smoke; includes the
experiment-resolve endpoint the engineer's suite did not cover."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import get_settings
from vencertia.domain import Action, Belief, Decision, DecisionOption, Project
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockSearchProvider, MockRetrievalProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, default_engine_bundle

BUSINESS_PREFIXES = ("/v1/", "/health")


@pytest.fixture
def client():
    settings = get_settings()
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    repo.save_project(Project(id="PRJ_QA", user_id="u1", name="QA project"))
    app = create_app(settings, repo, runtime)
    return TestClient(app), repo


def test_api_has_at_least_13_business_endpoints(client) -> None:
    tc, _ = client
    routes = [r.path for r in tc.app.routes if hasattr(r, "methods") and r.methods]
    business = [p for p in routes if p.startswith(BUSINESS_PREFIXES) and p != "/health"]
    assert len(business) >= 13, f"expected >=13 business endpoints, got {len(business)}: {business}"
    assert "/v1/solve" in business
    assert "/v1/experiments/{experiment_id}/resolve" in business


def test_experiment_resolve_endpoint_smoke(client) -> None:
    """POST /v1/experiments/{id}/resolve — not covered by the engineer's API tests."""
    tc, repo = client
    solve_r = tc.post("/v1/solve", json={
        "project_id": "PRJ_QA", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    assert solve_r.status_code == 200
    experiment = solve_r.json()["data"]["next_experiment"]["experiment"]
    experiment_id = experiment["id"]
    # The experiment is persisted by solve (EXPERIMENT_PROPOSED path).
    stored = repo.get_experiment(experiment_id)
    assert stored is not None
    # Set the decision link so resolve can attach the action correctly.
    decision_id = solve_r.json()["data"]["decision_id"]
    stored.decision_id = decision_id
    stored.version += 1
    repo.save_experiment(stored, expected_version=stored.version - 1)

    r = tc.post(f"/v1/experiments/{experiment_id}/resolve", json={
        "result": "0 paid", "quantitative": {"wtp": 0.0}, "outcome_type": "FAILURE"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["outcome"]["result"] == "0 paid"
    resolved = repo.get_experiment(experiment_id)
    assert resolved.status == "RESOLVED_REFUTE"


def test_stale_write_error_handler_registered(client) -> None:
    """StaleWriteError must be mapped to HTTP 409 by the app."""
    tc, repo = client
    from vencertia.repositories.base import StaleWriteError

    handler = tc.app.exception_handlers.get(StaleWriteError)
    assert handler is not None, "StaleWriteError handler must be registered (409)"
