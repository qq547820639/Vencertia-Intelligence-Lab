"""v1.1 API endpoint smoke tests (research/evidence-binding/sensitivity/trace)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, default_engine_bundle


@pytest.fixture
def client():
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    # Seed a solved decision so research/decision endpoints have data.
    result = runtime.solve(
        __import__("vencertia.runtime", fromlist=["SolveRequest"]).SolveRequest(
            project_id="PRJ_API11", problem_text="Should we commit six weeks to the MVP?", user_id="u1"
        )
    )
    app = create_app(settings, repo, runtime)
    return TestClient(app), repo, result


def test_health_reports_api_version(client):
    tc, _, _ = client
    r = tc.get("/health")
    assert r.status_code == 200
    data = r.json()["data"]
    # v1.2 (P1-12): single source of truth + legacy derived aliases.
    assert data["runtime_version"] == "1.5.0"
    assert data["api_contract_version"] == "1.4"
    assert data["version"] == "1.5.0"  # derived from vencertia.__version__
    assert data["api_version"] == "1.4.0"  # derived from api_contract_version


def test_research_plan_endpoint(client):
    tc, _, result = client
    r = tc.post("/v1/research/plan", json={"decision_id": result.decision_id})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"].startswith("RP_")


def test_research_run_endpoint(client):
    tc, _, result = client
    tc.post("/v1/research/plan", json={"decision_id": result.decision_id})
    r = tc.post("/v1/research/run", json={"decision_id": result.decision_id})
    assert r.status_code == 200
    # v1.1.2 (P0-5): /v1/research/run returns the full ResearchExecutionResult
    # (additive — the previous trace list is preserved inside ``traces``).
    data = r.json()["data"]
    assert isinstance(data, dict)
    assert "traces" in data
    assert isinstance(data["traces"], list)
    assert "applied_evidence" in data
    assert data["decision_id"] == result.decision_id


def test_evidence_bind_endpoint(client):
    tc, repo, _ = client
    evidence = repo.list_evidence()[0]
    r = tc.post("/v1/evidence/bind", json={"evidence_id": evidence.id, "auto_extract": True})
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, dict)
    assert "bindings" in data


def test_evidence_bindings_list_endpoint(client):
    tc, repo, _ = client
    evidence = repo.list_evidence()[0]
    r = tc.get(f"/v1/evidence/{evidence.id}/bindings")
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


def test_decision_sensitivity_endpoint(client):
    tc, _, result = client
    r = tc.get(f"/v1/decisions/{result.decision_id}/sensitivity")
    assert r.status_code == 200
    assert r.json()["data"]["robustness"] in ("ROBUST_DECISION", "MODERATE_DECISION", "FRAGILE_DECISION")


def test_decision_trace_endpoint(client):
    tc, _, result = client
    r = tc.get(f"/v1/decisions/{result.decision_id}/trace")
    assert r.status_code == 200
    assert r.json()["data"]["decision_id"] == result.decision_id


def test_belief_history_endpoint(client):
    tc, repo, _ = client
    belief = repo.get_beliefs("PRJ_API11")[0]
    r = tc.get(f"/v1/beliefs/{belief.id}/history")
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


def test_research_trace_endpoint(client):
    tc, _, result = client
    r = tc.get(f"/v1/research/{result.decision_id}/trace")
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


def test_candidate_validate_endpoint(client):
    """Deterministic fixture (P1-11): create the candidate explicitly instead of
    depending on whether the solve scenario happened to generate one."""
    from vencertia.domain import CandidateClaim

    tc, repo, _ = client
    candidate = CandidateClaim(
        id="CC_FIXTURE",
        statement="ICP has a severe recurring problem",
        scope="PROJECT",
        source_evidence_ids=["E_FIXTURE"],
        extraction_confidence=0.9,
        validation_status="PENDING",
    )
    repo.save_candidate_claim(candidate)
    r = tc.post(f"/v1/claims/candidates/{candidate.id}/validate")
    assert r.status_code == 200
    assert r.json()["data"]["validation_status"] == "VALIDATED"


def test_solve_v11_output_sections(client):
    tc, _, _ = client
    r = tc.post("/v1/solve", json={
        "project_id": "PRJ_API11B", "problem_text": "Should we commit six weeks to the MVP?", "user_id": "u1"})
    assert r.status_code == 200
    data = r.json()["data"]
    for key in (
        "why",
        "belief_snapshot",
        "what_could_change_my_mind",
        "research_performed",
        "evidence_used",
        "evidence_rejected",
        "success_criteria",
        "failure_criteria",
        "stop_condition",
    ):
        assert key in data, f"missing solve output section: {key}"
