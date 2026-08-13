"""v1.2 M0 hardening acceptance tests (M0-1~M0-4).

M0-1 env alias, M0-2 real stop signal, M0-3 API error envelope, M0-4 prediction
single-write. PostgreSQL parity (M0-5) lives in tests/test_postgres_parity.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.domain import (
    Belief,
    Decision,
    DecisionOption,
    DecisionResult,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, default_engine_bundle
from vencertia.runtime.prediction_ledger import PredictionLedger
from vencertia.runtime.research_stop import ResearchStopRule, RoundSummary

# ---------------------------------------------------------------------------
# M0-1 env alias
# ---------------------------------------------------------------------------


def test_m01_model_provider_legacy_alias(monkeypatch):
    monkeypatch.delenv("VENCERTIA_MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    with pytest.warns(DeprecationWarning):
        settings = Settings.from_env()
    assert settings.model_provider == "openai_compatible"


def test_m01_model_provider_prefers_new_name(monkeypatch):
    monkeypatch.setenv("VENCERTIA_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_PROVIDER", "legacy_provider")
    settings = Settings.from_env()
    assert settings.model_provider == "openai_compatible"


# ---------------------------------------------------------------------------
# M0-2 real decision_sensitivity_signal
# ---------------------------------------------------------------------------


def test_m02_decision_sensitivity_signal_flips_to_one(settings):
    """A recommendation flip (before != after) drives the signal to 1.0."""
    rule = ResearchStopRule(settings)
    before = DecisionResult(
        decision_id="DEC_1", status="GO", recommended_option_id="a",
        confidence=0.5, decision_margin=0.2,
    )
    after = DecisionResult(
        decision_id="DEC_1", status="GO", recommended_option_id="b",
        confidence=0.5, decision_margin=0.2,
    )
    summary = RoundSummary(
        applied_evidence=[],
        bindings=[],
        target_claim_ids=[],
        beliefs_before=[],
        beliefs_after=[],
        decision_result_before=before,
        decision_result_after=after,
    )
    report = rule.evaluate([], [], [], [], round_no=1, round_summary=summary)
    assert report.signals["decision_sensitivity_signal"] == 1.0


def test_m02_solve_writes_research_trace_stop_status():
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    runtime = SolveOrchestrator(
        repo=repo, bus=bus, model=MockProvider(),
        search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
    )
    result = runtime.solve(
        SolveRequest(
            project_id="PRJ_M02",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    traces = repo.list_research_traces(result.decision_id)
    assert traces, "solve must run at least one research round"
    assert all(t.stop_status for t in traces)


# ---------------------------------------------------------------------------
# M0-3 API error envelope
# ---------------------------------------------------------------------------


def _client():
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    app = create_app(settings, repo, runtime)
    return TestClient(app), repo, runtime


def test_m03_missing_decision_uses_envelope():
    tc, _, _ = _client()
    r = tc.get("/v1/decisions/DEC_MISSING")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == 404
    assert "message" in body
    assert "detail" not in body


def test_m03_already_settled_prediction_uses_envelope():
    tc, _, runtime = _client()
    result = runtime.solve(
        SolveRequest(
            project_id="PRJ_M03",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    prediction_id = result.predictions[0].id
    first = tc.post(f"/v1/predictions/{prediction_id}/resolve", json={"outcome": True})
    assert first.status_code == 200
    second = tc.post(f"/v1/predictions/{prediction_id}/resolve", json={"outcome": False})
    assert second.status_code == 400
    assert second.json()["code"] == 400
    assert "message" in second.json()


# ---------------------------------------------------------------------------
# M0-4 prediction single write
# ---------------------------------------------------------------------------


def _belief() -> Belief:
    return Belief(
        id="wtp", claim_id="CLM_WTP", statement="wtp", scope="PROJECT",
        project_id="PRJ_1", posterior=0.7, probability=0.7, alpha=7, beta=3,
        decision_relevant=True,
    )


def _decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"], horizon="short",
    )


def test_m04_register_does_not_persist(repo):
    ledger = PredictionLedger(repo)
    entries = ledger.register(
        _decision(), [_belief()], domain="finance", model_tag="gpt-4o", module_tag="decision"
    )
    assert len(entries) == 1
    assert repo.get_prediction(entries[0].id) is None
    assert entries[0].domain == "finance"
    assert entries[0].model_tag == "gpt-4o"
    assert entries[0].module_tag == "decision"


def test_m04_solve_persists_once_with_backfilled_fields():
    repo = InMemoryRepository()
    runtime = SolveOrchestrator(
        repo=repo, model=MockProvider(),
        search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
    )
    runtime.solve(
        SolveRequest(
            project_id="PRJ_M04",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
            domain="finance",
            model_tag="gpt-4o",
        )
    )
    predictions = repo.list_predictions("PRJ_M04")
    assert predictions
    for prediction in predictions:
        assert prediction.model_tag == "gpt-4o"
        assert prediction.domain == "finance"
        assert prediction.module_tag == "decision"
        assert prediction.version == 1
