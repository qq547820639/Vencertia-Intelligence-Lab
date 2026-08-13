"""API smoke tests for all v1.0 endpoints (14 + health)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import get_settings
from vencertia.domain import Action, Project
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, default_engine_bundle


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
    repo.save_project(Project(id="PRJ_API", user_id="u1", name="API project"))
    from vencertia.domain import Belief

    repo.save_belief(
        Belief(id="BLF_API", claim_id="CLM_API", statement="api belief", scope="PROJECT",
               project_id="PRJ_API", decision_relevant=True)
    )
    app = create_app(settings, repo, runtime)
    return TestClient(app), repo


def test_health(client):
    tc, _ = client
    r = tc.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["version"] == "1.9.0"


def test_compile(client):
    tc, _ = client
    r = tc.post("/v1/decisions/compile", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    assert r.status_code == 200
    assert r.json()["code"] == 0
    assert r.json()["data"]["decision"]["id"].startswith("DEC_")


def test_solve_endpoint(client):
    tc, _ = client
    r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["decision"]["status"] == "ABSTAIN"
    assert data["next_experiment"] is not None


def test_evaluate_decision(client):
    tc, _ = client
    solve_r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    decision_id = solve_r.json()["data"]["decision_id"]
    r = tc.post("/v1/decisions/evaluate", json={"decision_id": decision_id})
    assert r.status_code == 200
    assert r.json()["data"]["decision"]["decision_id"] == decision_id


def test_get_decision(client):
    tc, _ = client
    solve_r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    decision_id = solve_r.json()["data"]["decision_id"]
    r = tc.get(f"/v1/decisions/{decision_id}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == decision_id


def test_evidence_add(client):
    tc, _ = client
    r = tc.post("/v1/evidence", json={
        "evidence": {"id": "E_API1", "scope": "PROJECT", "evidence_type": "REAL_PAYMENT",
                     "source": "paid 200 EUR", "claim_ids": ["CLM_WTP"],
                     # v1.1.2 (P0-3): PROJECT evidence must carry project_id.
                     "project_id": "PRJ_API"}})
    assert r.status_code == 200
    assert r.json()["data"]["authority_level"] == "PROJECT_REALITY"


def test_evidence_add_rejects_project_scope_without_project_id(client):
    """P0-3: PROJECT evidence without project_id is rejected with HTTP 400."""
    tc, _ = client
    r = tc.post("/v1/evidence", json={
        "evidence": {"id": "E_API_NOPID", "scope": "PROJECT", "evidence_type": "REAL_PAYMENT",
                     "source": "paid 200 EUR", "claim_ids": ["CLM_MISSING"]}})
    assert r.status_code == 400


def test_outcomes_endpoint(client):
    tc, repo = client
    solve_r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    decision_id = solve_r.json()["data"]["decision_id"]
    repo.save_action(Action(id="ACT_API", project_id="PRJ_API", kind="EXPERIMENT",
                            description="pilot", decision_id=decision_id, experiment_id="EXP_API"))
    r = tc.post("/v1/outcomes", json={
        "action_id": "ACT_API", "result": "0 paid",
        "quantitative": {"wtp": 0.0}, "outcome_type": "FAILURE"})
    assert r.status_code == 200
    assert r.json()["data"]["outcome"]["result"] == "0 paid"


def test_experiment_propose(client):
    tc, _ = client
    solve_r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    decision_id = solve_r.json()["data"]["decision_id"]
    r = tc.post("/v1/experiments/propose", json={"decision_id": decision_id})
    assert r.status_code == 200
    assert r.json()["data"]["decision_insufficient"] is True


def test_predictions_endpoint(client):
    tc, _ = client
    solve_r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    decision_id = solve_r.json()["data"]["decision_id"]
    r = tc.post("/v1/predictions", json={"decision_id": decision_id})
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 1


def test_prediction_resolve_endpoint(client):
    tc, _ = client
    solve_r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    prediction_id = solve_r.json()["data"]["predictions"][0]["id"]
    r = tc.post(f"/v1/predictions/{prediction_id}/resolve", json={"outcome": False})
    assert r.status_code == 200
    assert r.json()["data"]["resolution"] in ("TRUE", "FALSE", "CANCELLED")


def test_calibration_endpoint(client):
    tc, _ = client
    r = tc.get("/v1/calibration")
    assert r.status_code == 200
    assert "data" in r.json()


def test_project_beliefs(client):
    tc, _ = client
    r = tc.get("/v1/projects/PRJ_API/beliefs")
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 1


def test_critical_uncertainties_endpoint(client):
    tc, _ = client
    tc.post("/v1/solve", json={
        "project_id": "PRJ_API", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    r = tc.get("/v1/projects/PRJ_API/critical-uncertainties")
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 1


def test_404_on_missing_decision(client):
    tc, _ = client
    r = tc.get("/v1/decisions/DEC_MISSING")
    assert r.status_code == 404


def test_404_message_localized(client):
    """T4: EntityNotFoundError envelope message is localized Chinese."""
    tc, _ = client
    r = tc.get("/v1/decisions/DEC_MISSING")
    assert r.status_code == 404
    assert r.json()["message"] == "未找到决策：DEC_MISSING"


def test_400_message_localized(client):
    """T4: ValueError envelope message is localized Chinese (参数错误 prefix)."""
    tc, _ = client
    r = tc.post("/v1/evidence", json={
        "evidence": {"id": "E_API_NOPID2", "scope": "PROJECT", "evidence_type": "REAL_PAYMENT",
                     "source": "paid 200 EUR", "claim_ids": ["CLM_MISSING"]}})
    assert r.status_code == 400
    assert r.json()["message"].startswith("参数错误")
