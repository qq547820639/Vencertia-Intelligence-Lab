"""v1.9 — decision-review dashboard (read-only aggregation endpoint)."""

from __future__ import annotations


def test_review_returns_dashboard_structure(api_client):
    r = api_client.get("/v1/review")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "ledger" in data
    assert "open_predictions" in data
    assert "calibration" in data
    # honest verdict even with zero settled samples
    assert data["calibration"]["verdict"]


def test_review_ledger_records_solve_recommendation(api_client):
    api_client.post(
        "/v1/solve?view=summary",
        json={"project_id": "PRJ_REV", "problem_text": "是否投入 6 周做 MVP？"},
    )
    data = api_client.get("/v1/review").json()["data"]
    assert len(data["ledger"]) >= 1
    rec = data["ledger"][0]
    assert rec["status"] == "RECOMMENDED"
    assert rec["status_zh"] == "已推荐"
    assert rec["decision_id"]
    # recommendation may be None when the engine verdict is TEST/HOLD (honest)


def test_review_ledger_rows_carry_decision_question(api_client):
    """v1.9: ledger rows are titled by the human question, not the option id."""
    api_client.post(
        "/v1/solve?view=summary",
        json={"project_id": "PRJ_REV_Q", "problem_text": "是否投入 6 周做 MVP？"},
    )
    data = api_client.get("/v1/review").json()["data"]
    rows = [r for r in data["ledger"] if r["decision_id"].startswith("DEC_")]
    assert rows, "expected at least one ledger row with a decision id"
    assert rows[0]["decision_question"] == "是否投入 6 周做 MVP？"
    assert rows[0]["created_at"]
