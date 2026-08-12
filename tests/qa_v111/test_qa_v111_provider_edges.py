"""QA v1.1.1 Iteration 2 — adversarial edge cases for providers + runtime.

Targets (QA task list):
  4. HTTP provider malformed payload (JSON shape ok, fields wrong)
  5. HTTP search timeout → graceful degradation, no pseudo-evidence
  6. research with no provider (search=None) → solve must not crash
"""

from __future__ import annotations

import httpx
import pytest

from vencertia.events.bus import EventBus
from vencertia.events.types import EventType
from vencertia.providers.errors import (
    ProviderEmptyResultError,
    ProviderSchemaMismatchError,
    ProviderTimeoutError,
)
from vencertia.providers.http_search import HttpSearchProvider
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
# 4. malformed payload: JSON structure ok, fields wrong
# ---------------------------------------------------------------------------


def test_results_array_with_items_missing_title_is_schema_mismatch():
    """List of dicts but none carries a usable title → SCHEMA_MISMATCH."""
    provider = _provider(lambda req: _json_response([{"wrong": 1}, {"other": "x"}]))
    with pytest.raises(ProviderSchemaMismatchError):
        provider.search("q")


def test_object_with_results_key_but_bad_items_is_schema_mismatch():
    provider = _provider(lambda req: _json_response({"results": [{"not_a_title": 1}]}))
    with pytest.raises(ProviderSchemaMismatchError):
        provider.search("q")


def test_single_object_with_wrong_fields_is_schema_mismatch():
    provider = _provider(lambda req: _json_response({"unexpected": "shape"}))
    with pytest.raises(ProviderSchemaMismatchError):
        provider.search("q")


def test_array_of_non_dict_items_reports_empty_not_schema():
    """DOCUMENTED BEHAVIOR (minor spec divergence): a JSON array of non-dict
    items is silently filtered to [] then reported EMPTY_RESULT instead of
    SCHEMA_MISMATCH. The provider docstring says schema mismatch should map to
    ProviderSchemaMismatchError; actual behavior for non-dict arrays is
    EMPTY_RESULT. Not data-loss (no evidence fabricated), but worth noting."""
    provider = _provider(lambda req: _json_response(["just-a-string", 42]))
    with pytest.raises(ProviderEmptyResultError):
        provider.search("q")


def test_results_key_with_non_list_value_is_schema_mismatch():
    provider = _provider(lambda req: _json_response({"results": "not-a-list"}))
    with pytest.raises(ProviderSchemaMismatchError):
        provider.search("q")


# ---------------------------------------------------------------------------
# 5. HTTP search timeout → structured error → graceful degradation
# ---------------------------------------------------------------------------


def test_timeout_raises_provider_timeout_error():
    def handler(request):
        raise httpx.ReadTimeout("read timed out", request=request)

    with pytest.raises(ProviderTimeoutError):
        _provider(handler).search("q")
    # ProviderTimeoutError is a ProviderError → runtime degrades gracefully.


def test_timeout_is_provider_error_subclass():
    assert issubclass(ProviderTimeoutError, Exception)
    from vencertia.providers.errors import ProviderError

    assert issubclass(ProviderTimeoutError, ProviderError)


class _TimeoutSearchProvider:
    """Search provider that always times out (structured ProviderError)."""

    name = "timeout_search"

    def search(self, query: str, k: int = 5):
        raise ProviderTimeoutError("search timed out")


def test_runtime_timeout_degrades_gracefully_no_pseudo_evidence():
    """A timeout at runtime → PROVIDER_FAILED event, no evidence fabricated,
    solve still returns a decision.

    retrieval=None so the ONLY possible evidence source is the failing search
    provider; evidence_used must stay empty (no pseudo-evidence)."""
    from vencertia.providers.mock import MockProvider

    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=_TimeoutSearchProvider(),
        retrieval=None,
    )
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_TO", problem_text="Should we commit six weeks to the MVP?", user_id="u1"
        )
    )
    event_types = [e.event_type for e in repo._events_since(0)]
    assert EventType.PROVIDER_FAILED.value in event_types
    # The failing provider contributed zero evidence (no fabrication).
    assert result.evidence_used == []
    traces = repo.list_research_traces(result.decision_id)
    assert any("search provider failed" in note for t in traces for note in t.notes)
    assert result.decision is not None


# ---------------------------------------------------------------------------
# 6. research with no provider (search=None) — solve must not crash
# ---------------------------------------------------------------------------


def test_solve_with_search_none_does_not_crash():
    """search=None + retrieval=None → research loop skipped, solve completes,
    evidence_used empty, decision still produced."""
    from vencertia.providers.mock import MockProvider

    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=None,
        retrieval=None,
    )
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_NOSRC",
            problem_text="Should we expand into Europe?",
            user_id="u1",
        )
    )
    assert result.decision is not None
    assert result.evidence_used == []
    traces = repo.list_research_traces(result.decision_id)
    # A research round may still have run (questions planned), but with zero
    # queries executed because no provider exists.
    for t in traces:
        assert t.queries_executed == 0
        assert t.results_retrieved == 0
