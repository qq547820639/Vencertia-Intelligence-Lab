"""v1.3 T2 — default 5-section contract + ABSTAIN four elements + view param."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import (
    SolveOrchestrator,
    SolveRequest,
    default_engine_bundle,
)
from vencertia.runtime.presentation import solve_summary

FIVE_KEYS = {"current_judgment", "rationale", "biggest_unknown", "next_step", "change_condition"}


def _orchestrator() -> SolveOrchestrator:
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    return SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )


def test_solve_summary_five_key_contract():
    orchestrator = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_S1",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
            mode="EXPLORE",
        )
    )
    s = solve_summary(result)
    assert set(s) >= FIVE_KEYS
    assert all(s[k] for k in FIVE_KEYS if k != "change_condition")
    assert len(s["change_condition"]) >= 1


def test_solve_summary_abstain_current_judgment():
    orchestrator = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_S2", problem_text="Should we commit?", user_id="u1")
    )
    assert result.decision.status == "ABSTAIN"
    s = solve_summary(result)
    assert s["current_judgment"] in {"ACT", "TEST", "HOLD", "WAIT", "STOP"}
    assert s["current_judgment"] == "TEST"  # ABSTAIN + next_experiment
    assert s["current_judgment_zh"] == "试验验证"
    assert s["decision_status"] == "ABSTAIN"


def test_solve_summary_abstain_four_elements():
    orchestrator = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_S3", problem_text="Should we commit?", user_id="u1")
    )
    s = solve_summary(result)
    assert s["why_not_decide"]
    assert s["lowest_cost_next_step"]
    assert s["stop_condition"]
    assert s["deadline"] == "未设置"
    assert s["stakes_class"] in {"HIGH", "MEDIUM", "LOW"}
    assert s["stakes_class_zh"]


def test_solve_summary_mode_wording_switch():
    orchestrator = _orchestrator()
    explore = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_S4", problem_text="Should we commit?", user_id="u1", mode="EXPLORE"
        )
    )
    s_explore = solve_summary(explore)
    assert s_explore["next_step"].startswith("最小验证动作")

    operate = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_S5", problem_text="Should we commit?", user_id="u1", mode="OPERATE"
        )
    )
    s_operate = solve_summary(operate)
    assert s_operate["next_step"].startswith("下一步行动")


def test_solve_summary_confidence_phrase_from_template():
    orchestrator = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_S6", problem_text="Should we commit?", user_id="u1")
    )
    s = solve_summary(result)
    assert "未校准" in s["confidence_phrase"]


# --- API view param ---------------------------------------------------------------


def _client() -> TestClient:
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
    return TestClient(create_app(settings, repo, runtime))


def test_solve_api_view_summary():
    tc = _client()
    r = tc.post(
        "/v1/solve?view=summary",
        json={"project_id": "PRJ_VS", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["view"] == "summary"
    assert set(data) >= FIVE_KEYS
    assert "decision" not in data
    assert "belief_snapshot" not in data


def test_solve_api_view_rejects_bogus():
    """v1.3: view is a strict enum; an unknown value is rejected with 422."""
    tc = _client()
    r = tc.post(
        "/v1/solve?view=bogus",
        json={"project_id": "PRJ_VB", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 422


def test_solve_api_default_full_unchanged():
    tc = _client()
    r = tc.post(
        "/v1/solve",
        json={"project_id": "PRJ_VF", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["advanced_view"] is None  # 默认 view=full 逐字节不变
    assert data["decision"]["status"] == "ABSTAIN"
    assert data["next_experiment"] is not None


def test_solve_api_advanced_still_full():
    tc = _client()
    r = tc.post(
        "/v1/solve?advanced=true",
        json={"project_id": "PRJ_VA", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 200
    assert isinstance(r.json()["data"]["advanced_view"], dict)
