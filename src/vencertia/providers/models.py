"""Provider protocols — framework-agnostic model/search/retrieval adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class SearchResult(VencertiaBaseModel):
    """Internal, provider-agnostic search result (GAP-02).

    Adapters MUST normalize any vendor DTO into this shape; vendor fields
    never leak into the domain. ``content``/``published_at``/``metadata``
    are optional (present only when the external response carries them).
    """

    title: str
    url: str = ""
    snippet: str = ""
    content: str = ""
    published_at: datetime | None = None
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=utcnow)


class Document(VencertiaBaseModel):
    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ModelProvider(Protocol):
    """LLM gateway protocol (domain never depends on a concrete provider)."""

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict: ...
    def complete(self, prompt: str) -> str: ...


@runtime_checkable
class SearchProvider(Protocol):
    def search(self, query: str, k: int = 5) -> list[SearchResult]: ...


@runtime_checkable
class RetrievalProvider(Protocol):
    def retrieve(self, query: str, k: int = 5) -> list[Document]: ...
