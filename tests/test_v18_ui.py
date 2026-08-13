"""v1.8 — zero-build web decision workbench (static UI + /v1/solve integration)."""

from __future__ import annotations


def test_index_serves_workbench(api_client):
    r = api_client.get("/")
    assert r.status_code == 200
    assert "决策复盘器" in r.text
    assert "solve-form" in r.text


def test_static_assets_served(api_client):
    js = api_client.get("/static/app.js")
    assert js.status_code == 200
    assert "v1/solve" in js.text
    css = api_client.get("/static/style.css")
    assert css.status_code == 200


def test_solve_summary_chinese_contract(api_client):
    """End-to-end: the same payload the UI posts returns the Chinese 5-section contract."""
    r = api_client.post(
        "/v1/solve?view=summary",
        json={"project_id": "PRJ_UI", "problem_text": "是否投入 6 周做 MVP？"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    for key in ("current_judgment_zh", "confidence_phrase", "rationale", "biggest_unknown", "next_step"):
        assert key in data, f"missing {key}"
    assert "model_critique" in data  # v1.7 key always present
    assert "experiment_voi" in data
    assert "personalization" in data


def test_solve_advanced_view_for_ui_toggle(api_client):
    r = api_client.post(
        "/v1/solve?advanced=true",
        json={"project_id": "PRJ_UI2", "problem_text": "是否进入新市场？", "mode": "OPERATE"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data.get("advanced_view") is not None
