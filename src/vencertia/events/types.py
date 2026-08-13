"""Domain events (Event Log, not Event Sourcing).

Events are written to the ``event_log`` table for audit/replay and dispatched
to in-process subscribers via the :class:`~vencertia.events.bus.EventBus`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class EventType(str, Enum):
    """Canonical event types emitted by the runtime."""

    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    BELIEF_UPDATED = "BELIEF_UPDATED"
    DECISION_CREATED = "DECISION_CREATED"
    DECISION_EVALUATED = "DECISION_EVALUATED"
    DECISION_RE_EVALUATED = "DECISION_RE_EVALUATED"
    EXPERIMENT_PROPOSED = "EXPERIMENT_PROPOSED"
    EXPERIMENT_STARTED = "EXPERIMENT_STARTED"
    EXPERIMENT_RESOLVED = "EXPERIMENT_RESOLVED"
    ACTION_CREATED = "ACTION_CREATED"
    OUTCOME_RECORDED = "OUTCOME_RECORDED"
    PREDICTION_CREATED = "PREDICTION_CREATED"
    PREDICTION_RESOLVED = "PREDICTION_RESOLVED"
    CALIBRATION_UPDATED = "CALIBRATION_UPDATED"
    PROJECT_STATE_CHANGED = "PROJECT_STATE_CHANGED"
    CONTEXT_INVALIDATED = "CONTEXT_INVALIDATED"
    FOUNDER_PROFILE_CHANGED = "FOUNDER_PROFILE_CHANGED"
    COMPANY_CASE_UPDATED = "COMPANY_CASE_UPDATED"
    # v1.1 research / binding / sensitivity / provider events
    RESEARCH_PLANNED = "RESEARCH_PLANNED"
    RESEARCH_STARTED = "RESEARCH_STARTED"
    RESEARCH_COMPLETED = "RESEARCH_COMPLETED"
    RESEARCH_EXHAUSTED = "RESEARCH_EXHAUSTED"
    EVIDENCE_BOUND_TO_CLAIM = "EVIDENCE_BOUND_TO_CLAIM"
    EVIDENCE_BINDING_REJECTED = "EVIDENCE_BINDING_REJECTED"
    DECISION_SENSITIVITY_COMPUTED = "DECISION_SENSITIVITY_COMPUTED"
    PROVIDER_SELECTED = "PROVIDER_SELECTED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    PREDICTION_CORRECTED = "PREDICTION_CORRECTED"
    # v1.2 decision ledger (V-2)
    DECISION_RECORDED = "DECISION_RECORDED"
    DECISION_OUTCOME_RECORDED = "DECISION_OUTCOME_RECORDED"


def new_event_id() -> str:
    """Generate an event id with the ``EV_`` prefix."""
    return "EV_" + uuid4().hex


class DomainEvent(VencertiaBaseModel):
    """A single auditable event record."""

    event_id: str = Field(default_factory=new_event_id)
    event_type: EventType
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str = "system"
    occurred_at: datetime = Field(default_factory=utcnow)
    seq: int | None = None  # assigned by the event log when persisted


def make_event(
    event_type: EventType,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
    actor: str = "system",
) -> DomainEvent:
    """Convenience factory for domain events."""
    return DomainEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        actor=actor,
    )
