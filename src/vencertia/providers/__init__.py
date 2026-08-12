"""Providers package: model/search/retrieval adapters."""

from __future__ import annotations

from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.providers.models import (
    Document,
    ModelProvider,
    RetrievalProvider,
    SearchProvider,
    SearchResult,
)
from vencertia.providers.openai_compatible import OpenAICompatibleProvider
from vencertia.providers.retrieval import RetrievalProvider as _RetrievalProvider
from vencertia.providers.search import SearchAdapter

__all__ = [
    "Document",
    "MockProvider",
    "MockRetrievalProvider",
    "MockSearchProvider",
    "ModelProvider",
    "OpenAICompatibleProvider",
    "RetrievalProvider",
    "SearchAdapter",
    "SearchProvider",
    "SearchResult",
]
