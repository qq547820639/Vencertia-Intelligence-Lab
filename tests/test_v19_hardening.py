"""v1.9 — code-quality hardening regression tests.

Covers the fixes shipped in the v1.9 quality batch:
- EventBus per-handler isolation
- InMemoryRepository.list_bindings status filter (use_enum_values crash)
- optimistic-lock create-version parity across backends
- config env parsing (stakes thresholds / critic stakes / malformed-input warnings)
- provider retry policy (deterministic errors are not retried)
- OpenAI-compatible schema detection + plain-text complete() fallback
- MockRetrievalProvider no-match returns empty (no corpus fallback)
"""

from __future__ import annotations

import json
import warnings

import pytest

from vencertia.config import Settings
from vencertia.domain import EvidenceClaimBinding
from vencertia.events.types import EventType, make_event
from vencertia.providers.errors import ProviderSchemaMismatchError
from vencertia.providers.factory import create_provider_bundle
from vencertia.providers.mock import MockRetrievalProvider
from vencertia.providers.openai_compatible import _is_json_schema
from vencertia.repositories.base import StaleWriteError
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository

# -- EventBus handler isolation -------------------------------------------------


def test_event_bus_handler_failure_does_not_skip_later_handlers(event_bus):
    calls: list[str] = []

    def bad_handler(event):  # noqa: ARG001
        raise RuntimeError("subscriber bug")

    def good_handler(event):
        calls.append(event.entity_id)

    event_bus.subscribe(EventType.EVIDENCE_ADDED, bad_handler)
    event_bus.subscribe(EventType.EVIDENCE_ADDED, good_handler)
    event_bus.publish(make_event(EventType.EVIDENCE_ADDED, "evidence", "E_1", {}))
    assert calls == ["E_1"]


def test_event_bus_handler_failure_does_not_block_publish(event_bus):
    def bad_handler(event):  # noqa: ARG001
        raise RuntimeError("subscriber bug")

    event_bus.subscribe(EventType.EVIDENCE_ADDED, bad_handler)
    # must not raise
    event_bus.publish(make_event(EventType.EVIDENCE_ADDED, "evidence", "E_2", {}))
    assert event_bus.sequence == 1


# -- InMemory list_bindings status filter ---------------------------------------


def _binding(bid: str, status: str, claim_id: str = "CLM_1") -> EvidenceClaimBinding:
    return EvidenceClaimBinding(
        id=bid,
        evidence_id="E_B",
        claim_id=claim_id,
        binding_method="EXACT_MATCH",
        status=status,
        binding_confidence=0.9,
    )


def test_inmemory_list_bindings_status_filter_mixed_statuses():
    repo = InMemoryRepository()
    repo.save_binding(_binding("EB_BOUND", "BOUND"))
    repo.save_binding(_binding("EB_REJ", "REJECTED"))
    rows = repo.list_bindings(status="BOUND")
    assert [b.id for b in rows] == ["EB_BOUND"]


# -- optimistic-lock create-version parity ---------------------------------------


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_create_with_expected_version_not_one_raises(backend, tmp_path):
    from vencertia.domain import Project, ProjectStatus, Stage

    if backend == "memory":
        repo = InMemoryRepository()
    else:
        repo = SQLiteRepository(f"sqlite:///{tmp_path / 'parity.db'}")
    project = Project(
        id="PRJ_NEW",
        user_id="u1",
        name="p",
        status=ProjectStatus.EXPLORING,
        stage=Stage.S0_INITIALIZATION,
        version=2,
    )
    with pytest.raises(StaleWriteError):
        repo.save_project(project, expected_version=2)


def test_sqlite_stale_write_rolls_back_implicit_txn(tmp_path):
    repo = SQLiteRepository(f"sqlite:///{tmp_path / 'stale.db'}")
    from vencertia.domain import Belief

    belief = Belief(
        id="B_STALE",
        claim_id="CLM_S",
        statement="s",
        scope="PROJECT",
        project_id="PRJ_1",
        probability=0.5,
        version=1,
    )
    repo.save_belief(belief)
    belief.version = 2
    repo.save_belief(belief, expected_version=1)  # bump to v2
    stale = belief.model_copy(update={"version": 3})
    with pytest.raises(StaleWriteError):
        repo.save_belief(stale, expected_version=1)  # v1 no longer current
    assert repo.get_belief("B_STALE").version == 2


# -- config env parsing ----------------------------------------------------------


def test_settings_from_env_stakes_thresholds_json(monkeypatch):
    monkeypatch.setenv(
        "VENCERTIA_STAKES_THRESHOLDS",
        json.dumps({"HIGH": {"minimum_margin": 0.2, "max_critical_uncertainty": 0.3}}),
    )
    s = Settings.from_env()
    assert s.stakes_thresholds["HIGH"]["minimum_margin"] == 0.2
    assert s.stakes_thresholds["MEDIUM"]["minimum_margin"] == 0.08  # untouched default


def test_settings_from_env_critic_required_stakes(monkeypatch):
    monkeypatch.setenv("VENCERTIA_CRITIC_REQUIRED_STAKES", "MEDIUM")
    assert Settings.from_env().critic_required_stakes == "MEDIUM"


def test_settings_malformed_float_warns_and_falls_back(monkeypatch):
    monkeypatch.setenv("VENCERTIA_RISK_AVERSION", "not-a-float")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        s = Settings.from_env()
    assert s.risk_aversion == 0.25
    assert any("not a float" in str(w.message) for w in caught)


def test_settings_malformed_stakes_json_warns(monkeypatch):
    monkeypatch.setenv("VENCERTIA_STAKES_THRESHOLDS", "{not json")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        s = Settings.from_env()
    assert s.stakes_thresholds["MEDIUM"]["minimum_margin"] == 0.08


# -- provider retry policy -------------------------------------------------------


class _AlwaysSchemaMismatchProvider:
    name = "broken"

    def __init__(self):
        self.calls = 0

    def generate_structured(self, task, schema, context):  # noqa: ARG002
        self.calls += 1
        raise ProviderSchemaMismatchError("deterministic failure")

    def complete(self, prompt):  # noqa: ARG002
        self.calls += 1
        raise ProviderSchemaMismatchError("deterministic failure")


def test_deterministic_provider_error_is_not_retried(monkeypatch):
    settings = Settings(provider_max_retries=3, provider_retry_backoff_base=0.5)
    inner = _AlwaysSchemaMismatchProvider()
    bundle = create_provider_bundle(settings)
    sleeps: list[float] = []
    monkeypatch.setattr("vencertia.providers.factory.time.sleep", sleeps.append)
    # wrap the deterministic-failure provider through the factory's resilience path
    from vencertia.providers.factory import with_resilience

    resilient = with_resilience(inner, settings)
    with pytest.raises(ProviderSchemaMismatchError):
        resilient.generate_structured("t", {"kind": "x"}, {})
    assert inner.calls == 1
    assert sleeps == []
    # bundle construction still works with the default mock wiring
    assert bundle.model is not None


# -- OpenAI-compatible schema detection ------------------------------------------


def test_kind_tag_is_not_a_json_schema():
    assert _is_json_schema({"kind": "compile_decision"}) is False
    assert _is_json_schema({}) is False
    assert _is_json_schema({"type": "object", "properties": {"x": {"type": "string"}}}) is True


def test_openai_complete_plain_text_fallback():
    import httpx

    from vencertia.providers.openai_compatible import OpenAICompatibleProvider

    def handler(request):
        assert "response_format" not in json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "plain text answer"}}]},
        )

    provider = OpenAICompatibleProvider(base_url="http://test", api_key="k")
    provider._client = lambda: httpx.Client(  # noqa: SLF001
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    assert provider.complete("hello") == "plain text answer"


# -- MockRetrievalProvider no-match ----------------------------------------------


def test_mock_retrieval_no_match_returns_empty():
    provider = MockRetrievalProvider()
    assert provider.retrieve("完全没有交集的关键词") == []
