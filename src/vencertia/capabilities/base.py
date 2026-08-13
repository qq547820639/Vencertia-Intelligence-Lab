"""Capability base — candidates only, no write authority (ADR-001)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from vencertia.domain import (
    Claim,
    Decision,
    Evidence,
    Experiment,
    ModelCritique,
    VencertiaBaseModel,
)
from vencertia.domain.context import ContextBundle


class CapabilityResult(VencertiaBaseModel):
    """Candidate outputs produced by a capability module."""

    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    decision_skeleton: Decision | None = None
    experiments: list[Experiment] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # V-3: structured model criticism (optional; None keeps old capabilities intact).
    critique: ModelCritique | None = None


@runtime_checkable
class Capability(Protocol):
    name: str

    def run(self, task: str, context: ContextBundle) -> CapabilityResult: ...
