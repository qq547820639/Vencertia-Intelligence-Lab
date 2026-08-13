"""Synchronous in-process event bus.

The bus dispatches :class:`DomainEvent` objects to subscribed handlers and,
optionally, to a persistence sink (the repository's ``append_event``) so every
published event is also written to the event log for audit/replay.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable

from vencertia.events.types import DomainEvent, EventType

EventHandler = Callable[[DomainEvent], None]
EventSink = Callable[[DomainEvent], None]

_logger = logging.getLogger("vencertia.events")


class EventBus:
    """Minimal synchronous publish/subscribe bus with an optional log sink."""

    def __init__(self, sink: EventSink | None = None) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._sink = sink
        self._sequence = 0

    @property
    def sequence(self) -> int:
        """Number of events published through this bus instance."""
        return self._sequence

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    def handlers_for(self, event_type: EventType) -> list[EventHandler]:
        """Return registered handlers for an event type."""
        return list(self._handlers.get(event_type, []))

    def publish(self, event: DomainEvent) -> None:
        """Dispatch an event to its sink and subscribed handlers.

        Handler isolation (v1.9): the sink write happens first, and every
        handler runs inside its own try/except — a failing handler is logged
        and the remaining handlers still run. A subscriber bug must never
        abort the audit stream or a caller's mutation batch.
        """
        self._sequence += 1
        if self._sink is not None:
            self._sink(event)
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - isolation boundary, see docstring
                _logger.exception(
                    "event handler failed for %s (handler=%r)", event.event_type, handler
                )

    def publish_many(self, events: list[DomainEvent]) -> None:
        """Publish several events in order."""
        for event in events:
            self.publish(event)

    def clear(self) -> None:
        """Remove all handlers (used in tests)."""
        self._handlers.clear()
