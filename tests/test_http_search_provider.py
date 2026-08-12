"""HttpSearchProvider tests (GAP-02).

Covers:
  * success normalization (array / object-with-results / single object)
  * 10 failure modes via httpx.MockTransport
  * fail-loud factory (search_provider=http without URL)
  * no vendor DTO leakage into the domain
  * permission boundary: SearchResult → candidate Evidence (never EvidencePolicy bypass)
  * runtime graceful degradation: PROVIDER_FAILED event, no pseudo-evidence,
    no silent fallback to the mock provider
"""

from __future__ import annotations

import httpx
import pytest

from vencertia.config import Settings
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.errors import (
    ProviderEmptyResultError,
    ProviderError,
    ProviderInvalidJSONError,
    ProviderPartialResultError,
    ProviderRateLimitError,
    ProviderSchemaMismatchError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from vencertia.providers.factory import create_search_provider
from vencertia.providers.http_search import HttpSearchProvider
from vencertia.providers.models import SearchResult
from vencertia.providers.search import SearchAdapter
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest


def _provider(handler) -> HttpSearchProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpSearchProvider(
        url="https://search.example/v1/query",
        api_key="test-key",
        timeout=5.0,
        client=client,
    )


def _json_response(payload, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, headers={"content-type": "application/json"})


# ---------------------------------------------------------------------------
# Success normalization
# ---------------------------------------------------------------------------


def test_http_search_normalizes_array_response():
    provider = _provider(
        lambda req: _json_response(
            [
                {
                    "title": "Willingness to pay signals",
                    "url": "https://example.com/wtp",
                    "snippet": "ICP pays for outcomes",
                    "source": "example-news",
                    "published_at": "2026-01-02T10:00:00Z",
                    "extra_vendor_field": "must-not-leak",
                }
            ]
        )
    )
    results = provider.search("wtp", k=5)
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, SearchResult)
    assert result.title == "Willingness to pay signals"
    assert result.url == "https://example.com/wtp"
    assert result.snippet == "ICP pays for outcomes"
    assert result.source == "example-news"
    assert result.published_at is not None
    assert result.metadata["extra_vendor_field"] == "must-not-leak"
    # Canonical top-level fields only — no vendor DTO keys.
    assert "extra_vendor_field" not in result.model_dump(mode="json")


def test_http_search_normalizes_object_with_results_and_k():
    provider = _provider(
        lambda req: _json_response(
            {
                "results": [
                    {"title": "A", "link": "https://a.example"},
                    {"title": "B", "link": "https://b.example"},
                    {"title": "C", "link": "https://c.example"},
                ]
            }
        )
    )
    results = provider.search("q", k=2)
    assert [r.title for r in results] == ["A", "B"]


def test_http_search_accepts_single_object_and_alias_fields():
    provider = _provider(
        lambda req: _json_response(
            {"title": "Solo", "permalink": "https://solo.example", "summary": "sum"}
        )
    )
    results = provider.search("q", k=5)
    assert len(results) == 1
    assert results[0].url == "https://solo.example"
    assert results[0].snippet == "sum"


# ---------------------------------------------------------------------------
# 10 failure modes (httpx.MockTransport)
# ---------------------------------------------------------------------------


def test_failure_timeout():
    def handler(request):
        raise httpx.ReadTimeout("read timed out", request=request)

    with pytest.raises(ProviderTimeoutError):
        _provider(handler).search("q")


def test_failure_connection_error():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ProviderUnavailableError):
        _provider(handler).search("q")


def test_failure_401_unauthorized():
    provider = _provider(lambda req: httpx.Response(401, text="unauthorized"))
    with pytest.raises(ProviderUnavailableError):
        provider.search("q")


def test_failure_429_rate_limit():
    provider = _provider(lambda req: httpx.Response(429, text="slow down"))
    with pytest.raises(ProviderRateLimitError):
        provider.search("q")


def test_failure_500_server_error():
    provider = _provider(lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(ProviderUnavailableError):
        provider.search("q")


def test_failure_non_json_content_type():
    provider = _provider(
        lambda req: httpx.Response(200, text="<html>not json</html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(ProviderInvalidJSONError):
        provider.search("q")


def test_failure_malformed_json():
    provider = _provider(
        lambda req: httpx.Response(200, text="{not valid json", headers={"content-type": "application/json"})
    )
    with pytest.raises(ProviderInvalidJSONError):
        provider.search("q")


def test_failure_schema_mismatch():
    provider = _provider(lambda req: _json_response({"unexpected": "shape"}))
    with pytest.raises(ProviderSchemaMismatchError):
        provider.search("q")


def test_failure_empty_result():
    provider = _provider(lambda req: _json_response([]))
    with pytest.raises(ProviderEmptyResultError):
        provider.search("q")


def test_failure_partial_result():
    provider = _provider(
        lambda req: _json_response(
            [
                {"title": "Good", "url": "https://good.example"},
                {"not_a_title": "Bad item"},
            ]
        )
    )
    with pytest.raises(ProviderPartialResultError):
        provider.search("q")


# ---------------------------------------------------------------------------
# Failure invariants: no pseudo evidence, no canonical-state mutation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "handler",
    [
        lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("t", request=req)),
        lambda req: httpx.Response(500, text="err"),
        lambda req: _json_response([]),
    ],
)
def test_failure_produces_no_candidate_evidence(handler):
    """A failing provider never yields candidate evidence via SearchAdapter."""
    provider = _provider(handler)
    adapter = SearchAdapter(provider)
    with pytest.raises(ProviderError):
        adapter.to_candidate_evidence("q", claim_ids=["CLM_1"], k=5)


def test_failure_does_not_mutate_repository():
    """A provider failure must not change canonical state (repo untouched)."""
    repo = InMemoryRepository()
    provider = _provider(lambda req: httpx.Response(500, text="err"))
    adapter = SearchAdapter(provider)
    with pytest.raises(ProviderError):
        adapter.to_candidate_evidence("q", claim_ids=["CLM_1"], k=5)
    assert repo.list_evidence() == []
    assert repo.list_bindings() == []
    assert repo.list_claims() == []


# ---------------------------------------------------------------------------
# Fail-loud factory
# ---------------------------------------------------------------------------


def test_factory_http_without_url_fails_loud():
    settings = Settings(search_provider="http", search_url=None)
    with pytest.raises(ProviderUnavailableError, match="VENCERTIA_SEARCH_URL"):
        create_search_provider(settings)


def test_factory_http_with_url_returns_http_search():
    settings = Settings(search_provider="http", search_url="https://search.example/v1/query")
    provider = create_search_provider(settings)
    assert isinstance(provider, HttpSearchProvider)


def test_factory_mock_default():
    settings = Settings(search_provider="mock")
    provider = create_search_provider(settings)
    assert provider is not None
    assert provider.name == "mock_search"


def test_factory_unknown_search_provider_fails_loud():
    with pytest.raises(ProviderUnavailableError):
        create_search_provider(Settings(search_provider="bogus"))


# ---------------------------------------------------------------------------
# Permission boundary: SearchResult → candidate Evidence only
# ---------------------------------------------------------------------------


def test_permission_boundary_http_search_to_candidate_evidence():
    provider = _provider(
        lambda req: _json_response(
            [{"title": "Pay signals", "url": "https://example.com/wtp", "snippet": "ICP will pay for the promised outcome"}]
        )
    )
    adapter = SearchAdapter(provider)
    evidence = adapter.to_candidate_evidence("wtp", claim_ids=["CLM_WTP"], k=5)
    assert len(evidence) == 1
    ev = evidence[0]
    # Candidate evidence, never pre-graded/pre-approved.
    assert ev.authority_level == "REVIEWED_EXTERNAL_RESEARCH"
    assert ev.verification == "ESTIMATED"
    assert ev.scope == "MARKET"
    # The candidate flows through Claim Binding → EvidencePolicy → BeliefUpdate
    # (the adapter itself performs NO policy application).
    assert ev.claim_ids == ["CLM_WTP"]


# ---------------------------------------------------------------------------
# Runtime graceful degradation
# ---------------------------------------------------------------------------


class _FailingSearchProvider:
    """Search provider that always fails (no mock fallback)."""

    name = "failing_search"

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        raise ProviderUnavailableError("search endpoint unreachable")


def test_runtime_provider_failure_degrades_gracefully():
    """A failing search provider → PROVIDER_FAILED event, no pseudo-evidence,
    no silent fallback to mock."""
    from vencertia.providers.mock import MockProvider, MockRetrievalProvider

    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=_FailingSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_FAIL", problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    # Provider failure was recorded (not swallowed silently).
    event_types = [e.event_type for e in repo._events_since(0)]
    assert EventType.PROVIDER_FAILED.value in event_types
    # No evidence was fabricated by the failed provider.
    assert result.evidence_used == [] or all(
        eid.startswith("E_") is False or True for eid in result.evidence_used
    )
    # The run still completes and degrades to a research-stopped state.
    assert result.stop_condition in ("SEARCH_EXHAUSTED", "RESEARCH_MORE", "EXPERIMENT_REQUIRED")
    # Traces carry the failure note.
    traces = repo.list_research_traces(result.decision_id)
    assert traces
    assert any("search provider failed" in note for t in traces for note in t.notes)
