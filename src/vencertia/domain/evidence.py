"""Evidence: immutable observation records gated by the EvidencePolicy."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import (
    AuthorityLevel,
    ConflictStatus,
    Direction,
    EvidenceType,
    Scope,
    VencertiaBaseModel,
    Verification,
    utcnow,
)


class Provenance(VencertiaBaseModel):
    source_id: str | None = None  # "S_..." source registration
    source_url: str | None = None
    tool: str | None = None
    actor: str | None = None
    raw_extract: str | None = None


class Evidence(VencertiaBaseModel):
    """Complete evidence object (immutable; corrections create new + SUPERSEDE)."""

    id: str  # E_...
    claim_ids: list[str] = Field(default_factory=list)
    scope: Scope
    evidence_type: EvidenceType
    provenance: Provenance = Field(default_factory=Provenance)
    source: str
    directness: float = Field(default=0.7, ge=0, le=1)
    reliability: float = Field(default=0.7, ge=0, le=1)
    relevance: float = Field(default=1.0, ge=0, le=1)
    strength: float = Field(default=0.8, ge=0, le=1)
    supports_or_contradicts: Direction = Direction.NEUTRAL
    independence_group: str | None = None
    observed_at: datetime = Field(default_factory=utcnow)
    conflict_status: ConflictStatus = ConflictStatus.NO_CONFLICT
    authority_level: AuthorityLevel = AuthorityLevel.MODEL_PRIOR
    verification: Verification = Verification.UNKNOWN
    transferability: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1

    @property
    def is_company_case(self) -> bool:
        return self.scope == Scope.COMPANY_CASE.value or self.scope == "COMPANY_CASE"
