"""Claim binding domain objects (ADR-008).

An :class:`EvidenceClaimBinding` is the persistent link between one evidence
record and one claim. ``UNBOUND_EVIDENCE`` is an explicit status: the evidence
is persisted for audit/re-processing but is never silently attached to a claim.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from vencertia.domain.base import ClaimType, Scope, VencertiaBaseModel, utcnow


class BindingMethod(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    LEXICAL_MATCH = "LEXICAL_MATCH"
    SEMANTIC_MATCH = "SEMANTIC_MATCH"
    MANUAL = "MANUAL"
    EXTRACTOR_INFERRED = "EXTRACTOR_INFERRED"


class BindingStatus(str, Enum):
    BOUND = "BOUND"
    UNBOUND_EVIDENCE = "UNBOUND_EVIDENCE"


class EvidenceClaimBinding(VencertiaBaseModel):
    """Persistent evidence→claim binding (one row per pair)."""

    id: str  # EB_...
    evidence_id: str
    claim_id: str | None = None  # None when status == UNBOUND_EVIDENCE
    binding_confidence: float = Field(ge=0, le=1)
    binding_method: BindingMethod = BindingMethod.EXTRACTOR_INFERRED
    status: BindingStatus = BindingStatus.BOUND
    model: str | None = None
    provider: str | None = None
    matched_at: datetime = Field(default_factory=utcnow)
    retry_count: int = 0
    version: int = 1


class CandidateClaim(VencertiaBaseModel):
    """Extractor output: a claim candidate that must pass deterministic
    validation before it may ever become a canonical :class:`Claim`."""

    id: str  # CC_...
    statement: str
    scope: Scope
    claim_type: ClaimType = ClaimType.HYPOTHESIS
    source_evidence_ids: list[str] = Field(default_factory=list)
    extractor_model: str | None = None
    extractor_provider: str | None = None
    extraction_confidence: float = Field(default=0.5, ge=0, le=1)
    validation_status: str = "PENDING"  # PENDING | VALIDATED | REJECTED
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1


class ClaimMatchResult(VencertiaBaseModel):
    """Outcome of matching one candidate against the existing claim set."""

    candidate: CandidateClaim
    matched_claim_ids: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)  # {claim_id: score}
    verdict: str = "NO_MATCH"  # EXISTING_MATCH | MULTIPLE_MATCH | NEW_CANDIDATE | NO_MATCH


class ClaimBindingInput(VencertiaBaseModel):
    """Input to the ClaimBindingEngine pipeline."""

    research_results: list[dict] = Field(default_factory=list)
    context: Any = None  # ContextBundle / ContextBundleV11 / serialized dict
    existing_claims: list[Any] = Field(default_factory=list)  # Claim | dict
    auto_extract: bool = True
    binding_confidence_threshold: float = 0.6


class ClaimBindingOutput(VencertiaBaseModel):
    """Output of the ClaimBindingEngine pipeline (candidates only)."""

    bindings: list[EvidenceClaimBinding] = Field(default_factory=list)
    unbound: list[EvidenceClaimBinding] = Field(default_factory=list)
    new_candidates: list[CandidateClaim] = Field(default_factory=list)
    applied_evidence: list[dict] = Field(default_factory=list)
    rejected_evidence: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
