"""ModelParameter — provenance + approval metadata for belief coefficients (V-1).

``belief_coefficients`` remains the backward-compatible ``dict[str, float]``
contract. ``belief_parameters`` is the additive layer that annotates each
coefficient with where it came from (provenance) and whether it was approved.
"""

from __future__ import annotations

from enum import Enum

from vencertia.domain.base import VencertiaBaseModel


class ProvenanceType(str, Enum):
    """Where a belief coefficient value came from."""

    USER_DEFINED = "USER_DEFINED"
    OBSERVED = "OBSERVED"
    DOMAIN_DEFAULT = "DOMAIN_DEFAULT"
    EMPIRICALLY_ESTIMATED = "EMPIRICALLY_ESTIMATED"
    LLM_PROPOSED = "LLM_PROPOSED"
    UNKNOWN = "UNKNOWN"


class ApprovalStatus(str, Enum):
    """Approval state of a model parameter (LLM proposes; humans/system approve)."""

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ModelParameter(VencertiaBaseModel):
    """A single belief coefficient annotated with provenance + approval state.

    Defaults reproduce v1.1.2 behavior: a bare float coefficient is treated as a
    DOMAIN_DEFAULT parameter that is already APPROVED (no approval gate blocks
    the deterministic mock loop).
    """

    value: float
    provenance: ProvenanceType = ProvenanceType.DOMAIN_DEFAULT
    status: ApprovalStatus = ApprovalStatus.APPROVED
    approved_by: str | None = None
    note: str | None = None


__all__ = ["ApprovalStatus", "ModelParameter", "ProvenanceType"]
