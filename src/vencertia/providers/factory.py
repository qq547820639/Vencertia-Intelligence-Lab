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


# ---------------------------------------------------------------------------
# Resilience wrapper (ADR-012)
# ---------------------------------------------------------------------------


class _ResilientModelProvider:
    """Wraps a ModelProvider with retry + structured error mapping."""

    name = "resilient"

    def __init__(self, inner: ModelProvider, settings: Settings) -> None:
        self._inner = inner
        self.settings = settings
        self.name = getattr(inner, "name", "provider")

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        last_error: Exception | None = None
        attempts = self.settings.provider_max_retries + 1
        for attempt in range(attempts):
            try:
                return self._inner.generate_structured(task, schema, context)
            except Exception as exc:  # noqa: BLE001 - provider boundary
                last_error = exc
                if attempt < attempts - 1:
                    delay = self.settings.provider_retry_backoff_base * (2**attempt)
                    time.sleep(delay)
        raise classify_provider_error(cast(Exception, last_error))

    def complete(self, prompt: str) -> str:
        last_error: Exception | None = None
        attempts = self.settings.provider_max_retries + 1
        for attempt in range(attempts):
            try:
                return self._inner.complete(prompt)
            except Exception as exc:  # noqa: BLE001 - provider boundary
                last_error = exc
                if attempt < attempts - 1:
                    delay = self.settings.provider_retry_backoff_base * (2**attempt)
                    time.sleep(delay)
        raise classify_provider_error(cast(Exception, last_error))


class _ResilientSearchProvider:
    name = "resilient_search"

    def __init__(self, inner: SearchProvider, settings: Settings) -> None:
        self._inner = inner
        self.settings = settings
        self.name = getattr(inner, "name", "provider")

    def search(self, query: str, k: int = 5):
        last_error: Exception | None = None
        attempts = self.settings.provider_max_retries + 1
        for attempt in range(attempts):
            try:
                return self._inner.search(query, k=k)
            except Exception as exc:  # noqa: BLE001 - provider boundary
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(self.settings.provider_retry_backoff_base * (2**attempt))
        raise classify_provider_error(cast(Exception, last_error))


class _ResilientRetrievalProvider:
    name = "resilient_retrieval"

    def __init__(self, inner: RetrievalProvider, settings: Settings) -> None:
        self._inner = inner
        self.settings = settings
        self.name = getattr(inner, "name", "provider")

    def retrieve(self, query: str, k: int = 5):
        last_error: Exception | None = None
        attempts = self.settings.provider_max_retries + 1
        for attempt in range(attempts):
            try:
                return self._inner.retrieve(query, k=k)
            except Exception as exc:  # noqa: BLE001 - provider boundary
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(self.settings.provider_retry_backoff_base * (2**attempt))
        raise classify_provider_error(cast(Exception, last_error))


def with_resilience(provider: Any, settings: Settings) -> Any:
    """Wrap any provider with retry + structured error mapping."""
    if isinstance(provider, (ModelProvider,)) and not isinstance(provider, _ResilientModelProvider):
        return _ResilientModelProvider(provider, settings)
    if isinstance(provider, SearchProvider) and not isinstance(provider, _ResilientSearchProvider):
        return _ResilientSearchProvider(provider, settings)
    if isinstance(provider, RetrievalProvider) and not isinstance(provider, _ResilientRetrievalProvider):
        return _ResilientRetrievalProvider(provider, settings)
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
    """Create the model provider selected by ``settings.model_provider``."""
    name = (settings.model_provider or "mock").lower()
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
    name = (settings.search_provider or "mock").lower()
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
    name = (settings.model_provider or "mock").lower()
    if name == "mock":
        return MockRetrievalProvider()
    return None


def create_provider_bundle(settings: Settings) -> ProviderBundle:
    """Build the full provider bundle and wrap it with resilience."""
    model = with_resilience(create_model_provider(settings), settings)
    search = create_search_provider(settings)
    if search is not None:
        search = with_resilience(search, settings)
    retrieval = create_retrieval_provider(settings)
    if retrieval is not None:
        retrieval = with_resilience(retrieval, settings)
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
