"""Claim binding domain objects (ADR-008).

An :class:`EvidenceClaimBinding` is the persistent link between one evidence
record and one claim. ``UNBOUND_EVIDENCE`` is an explicit status: the evidence
is persisted for audit/re-processing but is never silently attached to a claim.

v1.1.1 (GAP-01): :class:`BindingStatus` is a four-state contract:

- ``BOUND``            — at least one claim reached the binding threshold
                         (one evidence may bind many claims).
- ``AMBIGUOUS``        — the top-1/top-2 candidate gap is below
                         ``binding_ambiguity_margin``; forcing top-1 is forbidden.
- ``REJECTED``         — candidates existed but were explicitly rejected
                         (scope mismatch / policy violation / company-case
                         isolation violation / invalid evidence / claim
                         incompatibility / validation failure).
- ``UNBOUND_EVIDENCE`` — no candidate reached the minimum reliability score
                         (semantically distinct from REJECTED).

``UNBOUND`` remains a code-level name alias (maps to the canonical value;
it is NOT a literal-value alias — see :class:`BindingStatus`).
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
    AMBIGUOUS = "AMBIGUOUS"
    REJECTED = "REJECTED"
    UNBOUND_EVIDENCE = "UNBOUND_EVIDENCE"
    # Code-level name alias only (MINOR-CB-002): ``BindingStatus.UNBOUND`` maps
    # to the canonical value so older code that referenced the member NAME
    # keeps working and serializes to "UNBOUND_EVIDENCE". It is NOT a
    # literal-value alias: pydantic does not accept the string "UNBOUND" as
    # input (repo history always persisted "UNBOUND_EVIDENCE").
    UNBOUND = "UNBOUND_EVIDENCE"


class EvidenceClaimBinding(VencertiaBaseModel):
    """Persistent evidence→claim binding (one row per pair, GAP-01 trace).

    Each row also carries the full binding trace for its evidence:
    candidate_claim_ids / candidate_scores / selected_claim_ids / reason.
    """

    id: str  # EB_...
    evidence_id: str
    claim_id: str | None = None  # None when status in (AMBIGUOUS, REJECTED, UNBOUND_EVIDENCE)
    binding_confidence: float = Field(ge=0, le=1)
    binding_method: BindingMethod = BindingMethod.EXTRACTOR_INFERRED
    status: BindingStatus = BindingStatus.BOUND
    model: str | None = None
    provider: str | None = None
    matched_at: datetime = Field(default_factory=utcnow)
    retry_count: int = 0
    version: int = 1
    # -- v1.1.1 binding trace extension (GAP-01) -------------------------------
    candidate_claim_ids: list[str] = Field(default_factory=list)
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    selected_claim_ids: list[str] = Field(default_factory=list)
    reason: str = ""


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
    # GAP-01 per-call overrides (None → Settings defaults).
    binding_min_score: float | None = None
    binding_ambiguity_margin: float | None = None
    binding_reject_threshold: float | None = None


class ClaimBindingOutput(VencertiaBaseModel):
    """Output of the ClaimBindingEngine pipeline (candidates only)."""

    bindings: list[EvidenceClaimBinding] = Field(default_factory=list)
    unbound: list[EvidenceClaimBinding] = Field(default_factory=list)
    new_candidates: list[CandidateClaim] = Field(default_factory=list)
    applied_evidence: list[dict] = Field(default_factory=list)
    rejected_evidence: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
