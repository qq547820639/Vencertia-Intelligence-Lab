"""RetrievalProvider interface + mock (ADR-006: no vector dependency in v1.0)."""

from __future__ import annotations

from vencertia.providers.mock import MockRetrievalProvider
from vencertia.providers.models import Document, RetrievalProvider

__all__ = ["Document", "MockRetrievalProvider", "RetrievalProvider"]
