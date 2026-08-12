"""Default-container API smoke test (BLOCKER-API-001).

The documented run path is ``make api`` → ``uvicorn vencertia.api:app``, which
builds the DEFAULT container with a real ``SQLiteRepository`` (default DSN
``sqlite:///data/vencertia.db``). Starlette's TestClient executes sync route
handlers in worker threads, so a real SQLite connection created at startup in
the main thread must be usable from those worker threads.

Regression guard: this test wires the default container with a real
(file-backed) SQLite repository and POSTs /v1/solve — it must return 200,
not the pre-fix ``sqlite3.ProgrammingError`` HTTP 500 (cross-thread access).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from vencertia.config import Settings
from vencertia.container import build_container


def test_default_container_solve_returns_200_with_real_sqlite(tmp_path) -> None:
    settings = Settings(
        model_provider="mock",
        db_dsn=f"sqlite:///{tmp_path / 'smoke.db'}",
    )
    container = build_container(settings)
    client = TestClient(container.fastapi_app())

    response = client.post(
        "/v1/solve",
        json={
            "project_id": "PRJ_DEFAULT_CONTAINER",
            "problem_text": "Should we commit six weeks to the MVP?",
            "user_id": "u1",
        },
    )
    # BLOCKER-API-001: pre-fix this was HTTP 500
    # (sqlite3.ProgrammingError: SQLite objects created in a thread can only
    # be used in that same thread).
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["decision_id"]
    assert "why" in data


def test_default_container_health_reports_provider(tmp_path) -> None:
    settings = Settings(
        model_provider="mock",
        db_dsn=f"sqlite:///{tmp_path / 'health.db'}",
    )
    container = build_container(settings)
    client = TestClient(container.fastapi_app())
    body = client.get("/health").json()
    assert body["data"]["model_provider"] == "mock"
