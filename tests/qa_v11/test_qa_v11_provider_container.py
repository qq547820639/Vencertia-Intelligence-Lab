"""QA adversarial tests — Provider Composition Root + resilience (P0, ADR-009/012).

Verifies: MODEL_PROVIDER really decides the wired provider; API and CLI share
the same container (changing Settings changes API behavior); provider failure
does not pollute canonical state.
"""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.container import build_container
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.errors import ProviderError
from vencertia.providers.factory import (
    ProviderBundle,
    create_model_provider,
    create_provider_bundle,
    with_resilience,
)
from vencertia.providers.mock import MockProvider, MockSearchProvider
from vencertia.providers.openai_compatible import OpenAICompatibleProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest


def test_qa_model_provider_factory_follows_settings():
    """MODEL_PROVIDER=mock vs =openai_compatible produce different providers."""
    mock_provider = create_model_provider(Settings(model_provider="mock"))
    assert isinstance(mock_provider, MockProvider)

    oai = create_model_provider(
        Settings(model_provider="openai_compatible", openai_api_key=None, openai_base_url="http://localhost:9")
    )
    assert isinstance(oai, OpenAICompatibleProvider)


def test_qa_bundle_builds_for_both_providers():
    """create_provider_bundle works for mock and openai_compatible (no key).

    GAP-02: the search provider is selected independently by
    ``settings.search_provider`` (default ``mock``), so the bundle always
    wires a search adapter (never silently drops it).
    """
    bundle_mock = create_provider_bundle(Settings(model_provider="mock"))
    assert isinstance(bundle_mock, ProviderBundle)
    assert bundle_mock.model is not None
    assert bundle_mock.search is not None  # mock search wired

    bundle_oai = create_provider_bundle(
        Settings(model_provider="openai_compatible", openai_api_key=None)
    )
    assert isinstance(bundle_oai, ProviderBundle)
    # Search remains wired (search_provider defaults to mock independently of
    # the model gateway).
    assert bundle_oai.search is not None


def test_qa_container_provider_follows_settings_and_api_follows_container():
    """Changing Settings changes the provider the API/CLI container wires."""
    container_mock = build_container(Settings(model_provider="mock", db_dsn="sqlite:///:memory:"))
    assert container_mock.settings.model_provider == "mock"
    # The factory wraps providers with resilience; the underlying provider name
    # is preserved so the selection is observable.
    assert container_mock.providers.model.name == "mock"
    assert container_mock.providers.search is not None

    container_oai = build_container(
        Settings(model_provider="openai_compatible", openai_api_key=None, db_dsn="sqlite:///:memory:")
    )
    assert container_oai.providers.model is not None
    assert container_oai.orchestrator.model is container_oai.providers.model

    # API behavior follows the container: /health reports the selected provider.
    from fastapi.testclient import TestClient

    client = TestClient(container_mock.fastapi_app())
    body = client.get("/health").json()
    assert body["data"]["model_provider"] == "mock"

    client_oai = TestClient(container_oai.fastapi_app())
    body_oai = client_oai.get("/health").json()
    assert body_oai["data"]["model_provider"] == "openai_compatible"


class AlwaysFailsSearch(MockSearchProvider):
    """Search provider that always raises a transport-level error."""

    name = "always_fails"

    def search(self, query, k=5):
        raise TimeoutError("simulated provider timeout")


def test_qa_provider_failure_does_not_pollute_canonical_state():
    """GAP-02: a provider failure degrades gracefully — PROVIDER_FAILED is
    recorded and NO pseudo-evidence/binding from the failed provider is
    persisted (never a silent fallback to mock, never a fabricated result)."""
    settings = Settings(
        provider_max_retries=0,
        provider_retry_backoff_base=0.0,
        db_dsn="sqlite:///:memory:",
    )
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=with_resilience(AlwaysFailsSearch(), settings),  # wrapped like the factory does
        retrieval=None,
        settings=settings,
    )
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_FAIL", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    # The failure was recorded (structured event), not swallowed.
    event_types = [e.event_type for e in repo._events_since(0)]
    assert EventType.PROVIDER_FAILED.value in event_types
    # No research evidence / bindings from the failed search were persisted.
    assert repo.list_evidence() == []
    assert repo.list_bindings() == []
    assert repo.list_research_traces("whatever") == []
    # The solve still completed with a degraded (research-stopped) state.
    assert result.stop_condition in ("SEARCH_EXHAUSTED", "RESEARCH_MORE", "EXPERIMENT_REQUIRED")


def test_qa_resilience_maps_timeout_to_structured_error():
    """Raw TimeoutError is mapped to a structured ProviderError after retries."""
    class FailingModel(MockProvider):
        name = "failing_model"

        def generate_structured(self, task, schema, context):
            raise TimeoutError("boom")

    settings = Settings(provider_max_retries=1, provider_retry_backoff_base=0.0)
    wrapped = with_resilience(FailingModel(), settings)
    with pytest.raises(ProviderError):
        wrapped.generate_structured("compile", {"kind": "compile"}, {})


def test_qa_unknown_provider_fails_loud_not_silent_mock():
    """Unknown provider name must raise, never silently fall back to mock."""
    with pytest.raises(ProviderError):
        create_model_provider(Settings(model_provider="not_a_provider"))
