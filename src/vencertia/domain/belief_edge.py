"""BeliefEdge — declarative causal-graph edges between beliefs (V-6).

A :class:`BeliefEdge` records a typed relationship between two beliefs
(``source_belief_id`` → ``target_belief_id``) with a
:class:`BeliefRelationType`. Edges are declarative: they are persisted through
the generic ``entities`` table and projected into the advanced solve view
(``belief_graph``); the *execution* layer for anti-double-counting lives in the
``Evidence.shared_signal_group`` discount inside :mod:`vencertia.runtime.belief_engine`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class BeliefRelationType(str, Enum):
    """Nine typed belief relations (V-6 causal graph vocabulary)."""

    CAUSES = "CAUSES"
    DEPENDS_ON = "DEPENDS_ON"
    MEDIATES = "MEDIATES"
    MODERATES = "MODERATES"
    SHARES_LATENT_FACTOR = "SHARES_LATENT_FACTOR"
    SHARED_SIGNAL = "SHARED_SIGNAL"
    REDUNDANT_WITH = "REDUNDANT_WITH"
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"
    UNKNOWN_RELATIONSHIP = "UNKNOWN_RELATIONSHIP"


class BeliefEdge(VencertiaBaseModel):
    """A typed, optimistically-locked edge between two beliefs."""

    id: str  # BE_...
    decision_id: str | None = None  # optional: decision-level or global edge
    project_id: str | None = None
    source_belief_id: str
    target_belief_id: str
    relation: BeliefRelationType = BeliefRelationType.UNKNOWN_RELATIONSHIP
    note: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1  # optimistic lock


__all__ = ["BeliefEdge", "BeliefRelationType"]
