"""Provider Composition Root (ADR-009).

``Settings.model_provider`` decides which provider is wired. ``api.py`` and
``cli.py`` both build through :func:`create_provider_bundle`, so swapping the
model gateway never requires changing call sites. New providers register via
:func:`register_model_provider` (OSS admission path, ADR-006).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from vencertia.config import Settings
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
from vencertia.providers.http_search import HttpSearchProvider
from vencertia.providers.mock import (
    MockProvider,
    MockRetrievalProvider,
    MockSearchProvider,
)
from vencertia.providers.models import (
    ModelProvider,
    RetrievalProvider,
    SearchProvider,
)
from vencertia.providers.openai_compatible import OpenAICompatibleProvider

T = TypeVar("T")


class ProviderBundle(BaseModel):
    """Wired provider set for the whole application."""

    model: ModelProvider
    search: SearchProvider | None = None
    retrieval: RetrievalProvider | None = None

    model_config = {"arbitrary_types_allowed": True}


def classify_provider_error(exc: Exception) -> ProviderError:
    """Map low-level exceptions to the structured error taxonomy."""
    import httpx

    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return ProviderTimeoutError(str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response is not None and exc.response.status_code == 429:
            return ProviderRateLimitError(str(exc))
        if exc.response is not None and 500 <= exc.response.status_code < 600:
            return ProviderUnavailableError(str(exc))
        return ProviderUnavailableError(str(exc))
    if isinstance(exc, json.JSONDecodeError):
        return ProviderInvalidJSONError(str(exc))
    if isinstance(exc, ValueError):
        # pydantic ValidationError subclasses ValueError
        return ProviderSchemaMismatchError(str(exc))
    return ProviderUnavailableError(str(exc))


# Transient failures worth retrying (ADR-012). Deterministic failures (invalid
# JSON / schema mismatch / empty / partial results) will NEVER succeed on
# retry — retrying them only burns latency and hides the real error.
_RETRYABLE_ERRORS = (ProviderTimeoutError, ProviderRateLimitError, ProviderUnavailableError)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ProviderError):
        return isinstance(exc, _RETRYABLE_ERRORS)
    return True  # undecorated low-level exception: retry (bounded), classify after


def _retry_call(
    attempts: int, backoff_base: float, call, *args, **kwargs
) -> tuple[Any, int]:
    """Run ``call`` with bounded retry on transient failures only (v1.9).

    Returns ``(result, attempts_used)`` or raises the classified ProviderError.
    """
    attempts = max(1, attempts)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return call(*args, **kwargs), attempt + 1
        except Exception as exc:  # noqa: BLE001 - provider boundary
            last_error = exc
            if not _is_retryable(exc) or attempt >= attempts - 1:
                break
            time.sleep(backoff_base * (2**attempt))
    raise classify_provider_error(cast(Exception, last_error))


# ---------------------------------------------------------------------------
# Resilience wrapper (ADR-012) + recording (P1-7)
# ---------------------------------------------------------------------------


class _ResilientModelProvider:
    """Wraps a ModelProvider with retry + structured error mapping.

    v1.1.2 (P1-7): when a ``recorder`` is provided every call is recorded via
    CallRecorder (kind="model"); the actual retry count is captured.
    """

    name = "resilient"

    def __init__(self, inner: ModelProvider, settings: Settings, recorder=None) -> None:
        self._inner = inner
        self.settings = settings
        self.name = getattr(inner, "name", "provider")
        self.recorder = recorder
        self._model_name = getattr(inner, "model", "") or ""

    def _generate_structured_with_retries(
        self, task: str, schema: dict, context: dict
    ) -> tuple[dict, int]:
        return _retry_call(
            self.settings.provider_max_retries + 1,
            self.settings.provider_retry_backoff_base,
            self._inner.generate_structured,
            task,
            schema,
            context,
        )

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        if self.recorder is None:
            return self._generate_structured_with_retries(task, schema, context)[0]
        holder: dict[str, int] = {"retry_count": 0}

        def _do() -> dict:
            result, used = self._generate_structured_with_retries(task, schema, context)
            holder["retry_count"] = used - 1
            return result

        return self.recorder.record(
            kind="model",
            provider=self.name,
            model=self._model_name,
            task_kind="compile",
            fn=_do,
            retry_count=lambda: holder.get("retry_count", 0),
        )

    def _complete_with_retries(self, prompt: str) -> tuple[str, int]:
        return _retry_call(
            self.settings.provider_max_retries + 1,
            self.settings.provider_retry_backoff_base,
            self._inner.complete,
            prompt,
        )

    def complete(self, prompt: str) -> str:
        if self.recorder is None:
            return self._complete_with_retries(prompt)[0]
        holder: dict[str, int] = {"retry_count": 0}

        def _do() -> str:
            result, used = self._complete_with_retries(prompt)
            holder["retry_count"] = used - 1
            return result

        return self.recorder.record(
            kind="model",
            provider=self.name,
            model=self._model_name,
            task_kind="complete",
            fn=_do,
            retry_count=lambda: holder.get("retry_count", 0),
        )


class _ResilientSearchProvider:
    name = "resilient_search"

    def __init__(self, inner: SearchProvider, settings: Settings, recorder=None) -> None:
        self._inner = inner
        self.settings = settings
        self.name = getattr(inner, "name", "provider")
        self.recorder = recorder
        self._model_name = getattr(inner, "model", "") or ""

    def _search_with_retries(self, query: str, k: int) -> tuple[Any, int]:
        return _retry_call(
            self.settings.provider_max_retries + 1,
            self.settings.provider_retry_backoff_base,
            self._inner.search,
            query,
            k,
        )

    def search(self, query: str, k: int = 5):
        if self.recorder is None:
            return self._search_with_retries(query, k)[0]
        holder: dict[str, int] = {"retry_count": 0}

        def _do():
            result, used = self._search_with_retries(query, k)
            holder["retry_count"] = used - 1
            return result

        return self.recorder.record(
            kind="search",
            provider=self.name,
            model=self._model_name,
            task_kind="research_run",
            fn=_do,
            retry_count=lambda: holder.get("retry_count", 0),
        )


class _ResilientRetrievalProvider:
    name = "resilient_retrieval"

    def __init__(self, inner: RetrievalProvider, settings: Settings, recorder=None) -> None:
        self._inner = inner
        self.settings = settings
        self.name = getattr(inner, "name", "provider")
        self.recorder = recorder
        self._model_name = getattr(inner, "model", "") or ""

    def _retrieve_with_retries(self, query: str, k: int) -> tuple[Any, int]:
        return _retry_call(
            self.settings.provider_max_retries + 1,
            self.settings.provider_retry_backoff_base,
            self._inner.retrieve,
            query,
            k,
        )

    def retrieve(self, query: str, k: int = 5):
        if self.recorder is None:
            return self._retrieve_with_retries(query, k)[0]
        holder: dict[str, int] = {"retry_count": 0}

        def _do():
            result, used = self._retrieve_with_retries(query, k)
            holder["retry_count"] = used - 1
            return result

        return self.recorder.record(
            kind="retrieval",
            provider=self.name,
            model=self._model_name,
            task_kind="research_run",
            fn=_do,
            retry_count=lambda: holder.get("retry_count", 0),
        )


def with_resilience(provider: Any, settings: Settings, recorder=None) -> Any:
    """Wrap any provider with retry + structured error mapping (+ recording)."""
    if isinstance(provider, (ModelProvider,)) and not isinstance(provider, _ResilientModelProvider):
        return _ResilientModelProvider(provider, settings, recorder)
    if isinstance(provider, SearchProvider) and not isinstance(provider, _ResilientSearchProvider):
        return _ResilientSearchProvider(provider, settings, recorder)
    if isinstance(provider, RetrievalProvider) and not isinstance(provider, _ResilientRetrievalProvider):
        return _ResilientRetrievalProvider(provider, settings, recorder)
    return provider


# ---------------------------------------------------------------------------
# Registry (future OSS providers append here; ADR-006)
# ---------------------------------------------------------------------------

_MODEL_PROVIDER_REGISTRY: dict[str, Callable[[Settings], ModelProvider]] = {}


def register_model_provider(name: str, factory: Callable[[Settings], ModelProvider]) -> None:
    """Register a model provider factory under a settings key."""
    _MODEL_PROVIDER_REGISTRY[name] = factory


_SEARCH_PROVIDER_REGISTRY: dict[str, Callable[[Settings], SearchProvider]] = {}


def register_search_provider(name: str, factory: Callable[[Settings], SearchProvider]) -> None:
    """Register a search provider factory under a settings key (OSS admission)."""
    _SEARCH_PROVIDER_REGISTRY[name] = factory


def create_model_provider(settings: Settings) -> ModelProvider:
    """Create the model provider selected by ``settings.model_provider``.

    v2.0.1 (product ruling): the default is the real AI path
    (``openai_compatible``); ``mock`` is a TEST/DEVELOPMENT-ONLY explicit
    opt-in, never an implicit fallback.
    """
    name = (settings.model_provider or "openai_compatible").lower()
    if name == "mock":
        return MockProvider()
    if name == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout=settings.provider_timeout_seconds,
            settings=settings,
        )
    if name in _MODEL_PROVIDER_REGISTRY:
        return _MODEL_PROVIDER_REGISTRY[name](settings)
    # Unknown provider: fail loud with a structured error rather than silently
    # falling back to mock (which would hide configuration mistakes).
    raise ProviderUnavailableError(f"Unknown model_provider: {settings.model_provider!r}")


def create_search_provider(settings: Settings) -> SearchProvider | None:
    """Create the search provider selected by ``settings.search_provider``.

    GAP-02: ``http`` requires ``VENCERTIA_SEARCH_URL``; if it is missing the
    factory FAILS LOUD (ProviderUnavailableError) instead of silently falling
    back to the mock provider (which would hide a configuration mistake).
    """
    name = (settings.search_provider or "http").lower()
    if name == "mock":
        return MockSearchProvider()
    if name == "http":
        if not settings.search_url:
            raise ProviderUnavailableError(
                "search_provider=http requires VENCERTIA_SEARCH_URL to be set "
                "(fail loud; no silent fallback to the mock provider)"
            )
        return HttpSearchProvider(
            url=settings.search_url,
            api_key=settings.search_api_key,
            timeout=settings.search_timeout_seconds,
            settings=settings,
        )
    if name in _SEARCH_PROVIDER_REGISTRY:
        return _SEARCH_PROVIDER_REGISTRY[name](settings)
    # Unknown provider: fail loud with a structured error rather than silently
    # falling back to mock (which would hide configuration mistakes).
    raise ProviderUnavailableError(f"Unknown search_provider: {settings.search_provider!r}")


def create_retrieval_provider(settings: Settings) -> RetrievalProvider | None:
    """Create the retrieval provider for the configured gateway (may be None)."""
    name = (settings.model_provider or "openai_compatible").lower()
    if name == "mock":  # test/development-only explicit opt-in
        return MockRetrievalProvider()
    return None


def create_provider_bundle(settings: Settings, recorder=None) -> ProviderBundle:
    """Build the full provider bundle and wrap it with resilience.

    v1.1.2 (P1-7): when ``recorder`` (a CallRecorder) is provided, every
    model/search/retrieval call is recorded with metadata (never prompts or
    API keys).
    """
    model = with_resilience(create_model_provider(settings), settings, recorder)
    search = create_search_provider(settings)
    if search is not None:
        search = with_resilience(search, settings, recorder)
    retrieval = create_retrieval_provider(settings)
    if retrieval is not None:
        retrieval = with_resilience(retrieval, settings, recorder)
    return ProviderBundle(model=model, search=search, retrieval=retrieval)


def provider_name(provider: Any) -> str:
    """Best-effort provider name for observability records."""
    return getattr(provider, "name", type(provider).__name__)


__all__ = [
    "ProviderBundle",
    "ProviderEmptyResultError",
    "ProviderError",
    "ProviderInvalidJSONError",
    "ProviderPartialResultError",
    "ProviderRateLimitError",
    "ProviderSchemaMismatchError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "classify_provider_error",
    "create_model_provider",
    "create_provider_bundle",
    "create_retrieval_provider",
    "create_search_provider",
    "provider_name",
    "register_model_provider",
    "register_search_provider",
    "with_resilience",
]
