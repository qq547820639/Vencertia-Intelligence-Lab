"""v1.2 V-7 ActionState vocabulary + mode + Default/Advanced projection."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.domain import (
    ActionState,
    DecisionOption,
    DecisionType,
    SolveMode,
    map_decision_type_to_action_state,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import (
    SolveOrchestrator,
    SolveRequest,
    default_engine_bundle,
)

# --- ActionState enum -----------------------------------------------------------


def test_action_state_vocabulary():
    assert {m.value for m in ActionState} == {"ACT", "TEST", "HOLD", "WAIT", "STOP"}
    assert ActionState.ACT == "ACT"  # use_enum_values
    assert {m.value for m in SolveMode} == {"EXPLORE", "OPERATE"}


def test_map_decision_type_to_action_state():
    assert map_decision_type_to_action_state(DecisionType.GO) is ActionState.ACT
    assert map_decision_type_to_action_state(DecisionType.CONDITIONAL_GO) is ActionState.ACT
    assert map_decision_type_to_action_state(DecisionType.SELECT_OPTION) is ActionState.ACT
    assert map_decision_type_to_action_state(DecisionType.HOLD) is ActionState.HOLD
    assert (
        map_decision_type_to_action_state(DecisionType.ABSTAIN, has_next_experiment=True)
        is ActionState.TEST
    )
    assert map_decision_type_to_action_state(DecisionType.ABSTAIN) is ActionState.WAIT
    assert map_decision_type_to_action_state(DecisionType.PIVOT) is ActionState.STOP
    assert map_decision_type_to_action_state(DecisionType.KILL) is ActionState.STOP
    assert map_decision_type_to_action_state("bogus") is ActionState.HOLD


# --- option_kind / mode ----------------------------------------------------------


def test_option_kind_field():
    opt = DecisionOption(id="a", label="a", option_kind="WAIT")
    assert opt.option_kind == "WAIT"
    assert DecisionOption(id="b", label="b").option_kind is None
    legacy = DecisionOption.model_validate({"id": "c", "label": "c"})
    assert legacy.option_kind is None


def test_mode_field():
    assert SolveRequest(project_id="p", problem_text="q", mode="EXPLORE").mode == "EXPLORE"
    assert SolveRequest(project_id="p", problem_text="q").mode is None


# --- solve integration --------------------------------------------------------------


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


def test_solve_abstain_maps_to_test_and_echoes_mode():
    orchestrator = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_V7",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
            mode="EXPLORE",
        )
    )
    assert result.decision.status == "ABSTAIN"
    assert result.action_state == "TEST"  # ABSTAIN + next_experiment
    assert result.mode == "EXPLORE"
    assert result.advanced_view is not None
    option_ids = {s.option_id for s in result.decision.option_scores}
    assert set(result.advanced_view.utility.keys()) == option_ids


# --- API Default / Advanced ----------------------------------------------------------


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


def test_solve_api_default_strips_advanced_view():
    tc = _client()
    r = tc.post(
        "/v1/solve",
        json={"project_id": "PRJ_V7", "problem_text": "Should we commit?", "user_id": "u1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["advanced_view"] is None
    assert data["mode"] is None
    assert data["action_state"] in ("ACT", "TEST", "HOLD", "WAIT", "STOP")


def test_solve_api_advanced_includes_projection():
    tc = _client()
    r = tc.post(
        "/v1/solve?advanced=true",
        json={
            "project_id": "PRJ_V7B",
            "problem_text": "Should we commit?",
            "user_id": "u1",
            "mode": "EXPLORE",
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    advanced = data["advanced_view"]
    assert isinstance(advanced, dict)
    assert isinstance(advanced.get("belief_graph"), list)
    assert isinstance(advanced.get("utility"), dict)
    assert "sensitivity" in advanced
    assert "trace" in advanced
    # v1.3 T3: every belief_graph edge carries a Chinese relation label.
    for edge in advanced.get("belief_graph", []):
        assert "relation_zh" in edge
    assert data["mode"] == "EXPLORE"
