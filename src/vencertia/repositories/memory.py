"""In-memory repository (tests / prototyping). Semantics match SQLite.

Metadata (version/updated_at) is kept separate from the entity payload so
payloads always validate under ``extra="forbid"``.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Callable

from vencertia.domain.base import VencertiaBaseModel, utcnow
from vencertia.events.types import DomainEvent
from vencertia.repositories.base import EntityStoreMixin, StaleWriteError


class InMemoryRepository(EntityStoreMixin):
    """Non-persistent repository backed by plain dicts."""

    def __init__(self) -> None:
        # key -> {"payload": dict, "version": int, "updated_at": str}
        self._data: dict[tuple[str, str], dict[str, Any]] = {}
        self._events: list[DomainEvent] = []

    # -- primitives ----------------------------------------------------------

    def _load(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        row = self._data.get((entity_type, entity_id))
        if row is None:
            return None
        return copy.deepcopy(row["payload"])

    def _store(
        self,
        entity_type: str,
        obj: VencertiaBaseModel,
        expected_version: int | None = None,
    ) -> None:
        key = (entity_type, obj.id)
        existing = self._data.get(key)
        if expected_version is not None:
            if existing is not None:
                if existing["version"] != expected_version:
                    raise StaleWriteError(entity_type, obj.id, expected_version)
            elif expected_version != 1:
                raise StaleWriteError(entity_type, obj.id, expected_version)
        self._data[key] = {
            "payload": copy.deepcopy(obj.model_dump(mode="json")),
            "version": obj.version,
            "updated_at": utcnow().isoformat(),
        }

    def _list_all(self, entity_type: str) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(row["payload"])
            for key, row in self._data.items()
            if key[0] == entity_type
        ]

    def _delete(self, entity_type: str, entity_id: str) -> None:
        self._data.pop((entity_type, entity_id), None)

    def _append_event(self, event: DomainEvent) -> int:
        seq = len(self._events) + 1
        recorded = event.model_copy(update={"seq": seq})
        self._events.append(recorded)
        return seq

    def _events_since(self, after_seq: int) -> list[DomainEvent]:
        return [e for e in self._events if (e.seq or 0) > after_seq]

    def _txn(self, fn: Callable[[], None]) -> None:
        snapshot = copy.deepcopy(self._data)
        events_snapshot = copy.deepcopy(self._events)
        try:
            fn()
        except Exception:
            self._data = snapshot
            self._events = events_snapshot
            raise
