"""Claim: a falsifiable proposition, separated from evidence (many-to-many)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import ClaimStatus, ClaimType, Scope, VencertiaBaseModel, utcnow


class Claim(VencertiaBaseModel):
    id: str  # CLM_...
    statement: str
    scope: Scope
    claim_type: ClaimType = ClaimType.HYPOTHESIS
    project_id: str | None = None
    company_id: str | None = None  # when scope == COMPANY_CASE
    status: ClaimStatus = ClaimStatus.ACTIVE
    supersedes_claim_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1
