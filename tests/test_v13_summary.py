"""v1.3 T2 — default 5-section contract + ABSTAIN four elements + view param."""

from __future__ import annotations

from tests.conftest import FIVE_KEYS
from vencertia.runtime import SolveRequest
from vencertia.runtime.presentation import solve_summary


def test_solve_summary_five_key_contract(orchestrator):
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


def test_solve_summary_abstain_current_judgment(orchestrator):
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_S2", problem_text="Should we commit?", user_id="u1")
    )
    assert result.decision.status == "ABSTAIN"
    s = solve_summary(result)
    assert s["current_judgment"] in {"ACT", "TEST", "HOLD", "WAIT", "STOP"}
    assert s["current_judgment"] == "TEST"  # ABSTAIN + next_experiment
    assert s["current_judgment_zh"] == "试验验证"
    assert s["decision_status"] == "ABSTAIN"


def test_solve_summary_abstain_four_elements(orchestrator):
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


def test_solve_summary_mode_wording_switch(orchestrator):
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


def test_solve_summary_confidence_phrase_from_template(orchestrator):
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_S6", problem_text="Should we commit?", user_id="u1")
    )
    s = solve_summary(result)
    assert "未校准" in s["confidence_phrase"]


# --- API view param ---------------------------------------------------------------


def test_solve_api_view_summary(api_client):
    r = api_client.post(
        "/v1/solve?view=summary",
        json={"project_id": "PRJ_VS", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["view"] == "summary"
    assert set(data) >= FIVE_KEYS
    assert "decision" not in data
    assert "belief_snapshot" not in data


def test_solve_api_view_rejects_bogus(api_client):
    """v1.3: view is a strict enum; an unknown value is rejected with 422."""
    r = api_client.post(
        "/v1/solve?view=bogus",
        json={"project_id": "PRJ_VB", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 422


def test_solve_api_default_full_unchanged(api_client):
    r = api_client.post(
        "/v1/solve",
        json={"project_id": "PRJ_VF", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["advanced_view"] is None  # 默认 view=full 逐字节不变
    assert data["decision"]["status"] == "ABSTAIN"
    assert data["next_experiment"] is not None


def test_solve_api_advanced_still_full(api_client):
    r = api_client.post(
        "/v1/solve?advanced=true",
        json={"project_id": "PRJ_VA", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 200
    assert isinstance(r.json()["data"]["advanced_view"], dict)
