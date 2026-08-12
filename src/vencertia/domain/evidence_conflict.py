"""Evidence conflict records (v1.1)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class ConflictType(str, Enum):
    DIRECT_CONTRADICTION = "DIRECT_CONTRADICTION"
    TEMPORAL = "TEMPORAL"
    CAUSAL = "CAUSAL"
    NUMERIC = "NUMERIC"


class EvidenceConflict(VencertiaBaseModel):
    """Explicit conflict between supporting and contradicting evidence for one claim."""

    id: str  # ECF_...
    claim_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    conflict_type: ConflictType = ConflictType.DIRECT_CONTRADICTION
    severity: float = Field(ge=0, le=1)
    resolution_status: str = "OPEN"  # OPEN | RESOLVED | SUPERSEDED
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    version: int = 1
