"""v1.9.1 — decision review loop (RECOMMENDED → ACTED → SETTLED) tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, default_engine_bundle


@pytest.fixture
def client_and_repo():
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


def _solved_decision_id(client, project_id: str) -> str:
    r = client.post(
        "/v1/solve?view=summary",
        json={"project_id": project_id, "problem_text": "是否投入 6 周做 MVP？"},
    )
    assert r.status_code == 200, r.text
    # the summary projection does not echo the decision id — read it back from
    # the review ledger (the same lookup the UI performs); each test runs on a
    # fresh repository, so the first ledger row is the freshly solved decision.
    review = client.get("/v1/review").json()["data"]
    rows = [rd for rd in review["ledger"] if rd.get("decision_id")]
    assert rows, "review ledger must contain the freshly solved decision"
    return rows[0]["decision_id"]


def test_act_marks_record_acted(client_and_repo):
    client, repo = client_and_repo
    decision_id = _solved_decision_id(client, "PRJ_ACT")
    r = client.post(
        f"/v1/decisions/{decision_id}/act",
        json={"action_taken": "先做 2 周访谈验证"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "ACTED"
    assert data["status_zh"] == "已行动"

    record = repo.get_decision_record(decision_id)
    assert record is not None and record.status == "ACTED"
    action = repo.get_action(record.action_taken)
    assert action is not None and action.description == "先做 2 周访谈验证"

    types = {e.event_type for e in repo.events_since(0)}
    assert EventType.DECISION_ACTED in types


def test_act_with_result_settles_closed_loop(client_and_repo):
    client, repo = client_and_repo
    decision_id = _solved_decision_id(client, "PRJ_SETTLE")
    r = client.post(
        f"/v1/decisions/{decision_id}/act",
        json={"action_taken": "投入 6 周构建 MVP", "result": "两周内获得 2 个付费试点", "outcome_type": "SUCCESS"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "SETTLED"
    assert data["status_zh"] == "已复盘"
    assert data.get("settlement") is not None

    record = repo.get_decision_record(decision_id)
    assert record is not None and record.status == "SETTLED"
    outcomes = repo.list_decision_outcome_records(record.id)
    assert len(outcomes) == 1
    types = {e.event_type for e in repo.events_since(0)}
    assert EventType.DECISION_ACTED in types
    assert EventType.DECISION_OUTCOME_RECORDED in types


def test_act_then_settle_second_call(client_and_repo):
    client, repo = client_and_repo
    decision_id = _solved_decision_id(client, "PRJ_TWOSTEP")
    first = client.post(
        f"/v1/decisions/{decision_id}/act", json={"action_taken": "做了试点"}
    )
    assert first.status_code == 200 and first.json()["data"]["status"] == "ACTED"
    second = client.post(
        f"/v1/decisions/{decision_id}/act",
        json={"action_taken": "做了试点", "result": "试点失败", "outcome_type": "FAILURE"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["status"] == "SETTLED"


def test_act_twice_settled_rejected(client_and_repo):
    client, _ = client_and_repo
    decision_id = _solved_decision_id(client, "PRJ_DOUBLE")
    r1 = client.post(
        f"/v1/decisions/{decision_id}/act",
        json={"action_taken": "a", "result": "r", "outcome_type": "PARTIAL"},
    )
    assert r1.status_code == 200
    r2 = client.post(f"/v1/decisions/{decision_id}/act", json={"action_taken": "again"})
    assert r2.status_code == 400
    assert "已复盘" in r2.json()["message"]


def test_act_unknown_decision_404(client_and_repo):
    client, _ = client_and_repo
    r = client.post("/v1/decisions/DEC_MISSING/act", json={"action_taken": "x"})
    assert r.status_code == 404


def test_ui_wires_act_forms_and_calib_chart(api_client):
    js = api_client.get("/static/app.js")
    assert js.status_code == 200
    assert "标记行动" in js.text
    assert "记录结果" in js.text
    assert "/v1/decisions/" in js.text
    assert "renderCalibChart" in js.text
    html = api_client.get("/")
    assert "calib-chart" in html.text
