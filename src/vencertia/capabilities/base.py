"""Capability base — candidates only, no write authority (ADR-001)."""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from pydantic import Field

from vencertia.domain import Claim, Decision, Evidence, Experiment, VencertiaBaseModel
from vencertia.runtime.context import ContextBundle


class CapabilityResult(VencertiaBaseModel):
    """Candidate outputs produced by a capability module."""

    claims: List[Claim] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    decision_skeleton: Optional[Decision] = None
    experiments: List[Experiment] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


@runtime_checkable
class Capability(Protocol):
    name: str

    def run(self, task: str, context: ContextBundle) -> CapabilityResult: ...
