"""EvidencePolicy — the first deterministic gate for evidence entry.

Assigns authority, applies scope gates (Company Case isolation, LLM downgrade),
and computes effective weights. Versioned per policy_version (docs/evidence-policy.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    AuthorityLevel,
    Evidence,
    EvidenceType,
    RuleSet,
    Scope,
    Verification,
)

# Authority hierarchy (v1.0) — 9 levels, versioned.
AUTHORITY_TABLE: dict[str, float] = {
    AuthorityLevel.PROJECT_REALITY.value: 1.00,
    AuthorityLevel.PROJECT_DIRECT_BEHAVIOR.value: 0.95,
    AuthorityLevel.PROJECT_EXPERIMENT_RESULT.value: 0.90,
    AuthorityLevel.CUSTOMER_COMMITMENT_OR_PAYMENT.value: 0.88,
    AuthorityLevel.ELIGIBLE_EXTERNAL_CASE_FACT.value: 0.75,
    AuthorityLevel.REVIEWED_EXTERNAL_RESEARCH.value: 0.65,
    AuthorityLevel.FOUNDER_STATEMENT.value: 0.45,
    AuthorityLevel.LLM_INFERENCE.value: 0.20,
    AuthorityLevel.MODEL_PRIOR.value: 0.10,
}

VERIFICATION_MULTIPLIER: dict[str, float] = {
    Verification.VERIFIED.value: 1.0,
    Verification.ESTIMATED.value: 0.75,
    Verification.ASSUMED.value: 0.35,
    Verification.UNKNOWN.value: 0.20,
}

# EvidenceType -> default AuthorityLevel (docs §3 mapping table)
EVIDENCE_TYPE_TO_AUTHORITY: dict[str, AuthorityLevel] = {
    EvidenceType.REAL_PAYMENT.value: AuthorityLevel.PROJECT_REALITY,
    EvidenceType.CONTRACT.value: AuthorityLevel.PROJECT_REALITY,
    EvidenceType.OBSERVED_BEHAVIOR.value: AuthorityLevel.PROJECT_DIRECT_BEHAVIOR,
    EvidenceType.EXPERIMENT_RESULT.value: AuthorityLevel.PROJECT_EXPERIMENT_RESULT,
    EvidenceType.CUSTOMER_COMMITMENT.value: AuthorityLevel.CUSTOMER_COMMITMENT_OR_PAYMENT,
    EvidenceType.OFFICIAL_DATA.value: AuthorityLevel.REVIEWED_EXTERNAL_RESEARCH,
    EvidenceType.PRIMARY_RESEARCH.value: AuthorityLevel.REVIEWED_EXTERNAL_RESEARCH,
    EvidenceType.REVIEWED_EXTERNAL_RESEARCH.value: AuthorityLevel.REVIEWED_EXTERNAL_RESEARCH,
    EvidenceType.ELIGIBLE_EXTERNAL_CASE_FACT.value: AuthorityLevel.ELIGIBLE_EXTERNAL_CASE_FACT,
    EvidenceType.COMPANY_CASE_FACT.value: AuthorityLevel.MODEL_PRIOR,  # project-side unavailable
    EvidenceType.FOUNDER_STATEMENT.value: AuthorityLevel.FOUNDER_STATEMENT,
    EvidenceType.EXPERT_INPUT.value: AuthorityLevel.REVIEWED_EXTERNAL_RESEARCH,
    EvidenceType.LLM_INFERENCE.value: AuthorityLevel.LLM_INFERENCE,
    EvidenceType.MODEL_PRIOR.value: AuthorityLevel.MODEL_PRIOR,
    EvidenceType.SYSTEM_DERIVED.value: AuthorityLevel.PROJECT_REALITY,
}

# Scopes that company-case evidence may update without transferability.
COMPANY_CASE_ALLOWED_SCOPES = {Scope.WORLD.value, Scope.MARKET.value, Scope.COMPANY_CASE.value}


@dataclass
class EvidenceGrade:
    """Result of grading an evidence record."""

    evidence: Evidence
    authority_level: AuthorityLevel
    effective_weight: float
    scope_gate: str  # OK | COMPANY_CASE_PRIOR_ONLY | REJECTED
    reason: str
    freshness_discount: float = 1.0  # v1.1


class EvidencePolicy:
    """Versioned authority table + scope gates."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def version(self) -> str:
        return self.settings.policy_version

    def weight_of(self, authority_level: str | AuthorityLevel) -> float:
        key = authority_level.value if hasattr(authority_level, "value") else str(authority_level)
        return AUTHORITY_TABLE.get(key, 0.10)

    def verification_multiplier(self, verification: str | Verification) -> float:
        key = verification.value if hasattr(verification, "value") else str(verification)
        return VERIFICATION_MULTIPLIER.get(key, 0.20)

    def freshness_factor(self, evidence: Evidence, now=None) -> float:
        """v1.1 freshness discount:
        - 0 if now > valid_until
        - 1 if now within [valid_from, valid_until]
        - exp(-age_days / freshness_half_life_days) otherwise
        - 1.0 when no validity window is set
        """
        from datetime import datetime

        now = now or datetime.now(UTC)
        if evidence.valid_until is not None and now > evidence.valid_until:
            return 0.0
        if evidence.valid_from is not None and now < evidence.valid_from:
            return 0.0
        reference = evidence.observed_at or evidence.published_at or evidence.created_at
        if reference is None or evidence.valid_until is None:
            return 1.0
        age_days = max(0.0, (now - reference).total_seconds() / 86400.0)
        half_life = max(1.0, float(self.settings.freshness_half_life_days))
        return round(max(0.0, min(1.0, math.exp(-age_days / half_life))), 6)

    # -- grading -------------------------------------------------------------

    def grade(
        self,
        evidence: Evidence,
        policy: RuleSet | None = None,
        project_context: dict[str, Any] | None = None,
        now=None,
    ) -> EvidenceGrade:
        """Assign authority + weight and run scope gates.

        Company-case evidence that fails transferability is gated to
        ``COMPANY_CASE_PRIOR_ONLY`` (may only update WORLD/MARKET priors).
        """
        authority = self._default_authority(evidence)
        verification = (
            evidence.verification
            if hasattr(evidence.verification, "value")
            else Verification(evidence.verification)
        )

        # LLM downgrade: model outputs can never self-declare VERIFIED.
        if evidence.evidence_type in (EvidenceType.LLM_INFERENCE, EvidenceType.MODEL_PRIOR):
            if verification == Verification.VERIFIED:
                verification = Verification.ESTIMATED

        # Company Case scope gate.
        if evidence.scope == Scope.COMPANY_CASE.value or evidence.is_company_case:
            return self.check_company_case_transferability(evidence, project_context or {})

        freshness = self.freshness_factor(evidence, now=now)
        weight = (
            self.weight_of(authority)
            * self.verification_multiplier(verification)
            * evidence.directness
            * evidence.reliability
            * evidence.relevance
            * evidence.strength
            * freshness
        )
        return EvidenceGrade(
            evidence=evidence,
            authority_level=authority,
            effective_weight=weight,
            scope_gate="OK",
            reason=f"authority={authority.value}, verification={verification.value}",
            freshness_discount=freshness,
        )

    def apply_authority(self, evidence: Evidence, policy_version: str) -> Evidence:
        """Return a copy of evidence with authority_level written back."""
        grade = self.grade(evidence)
        updated = evidence.model_copy(
            update={
                "authority_level": grade.authority_level.value,
                "verification": (
                    grade.evidence.verification
                    if not (
                        evidence.evidence_type
                        in (EvidenceType.LLM_INFERENCE, EvidenceType.MODEL_PRIOR)
                        and evidence.verification == Verification.VERIFIED
                    )
                    else Verification.ESTIMATED.value
                ),
            }
        )
        return updated

    def check_company_case_transferability(
        self,
        evidence: Evidence,
        project_context: dict[str, Any],
    ) -> EvidenceGrade:
        """Gate company-case evidence on transferability (docs §4.1, ADR-004)."""
        threshold = float(
            project_context.get("transferability_threshold")
            or self.settings.transferability_threshold
        )
        transferability = evidence.transferability
        if transferability is None or transferability < threshold:
            return EvidenceGrade(
                evidence=evidence,
                authority_level=AuthorityLevel.MODEL_PRIOR,
                effective_weight=0.0,
                scope_gate="COMPANY_CASE_PRIOR_ONLY",
                reason=(
                    "Company-case evidence without transferability >= "
                    f"{threshold} can only update WORLD/MARKET priors."
                ),
            )
        # Eligible: upgrade to ELIGIBLE_EXTERNAL_CASE_FACT (0.75) — still prior-only.
        authority = AuthorityLevel.ELIGIBLE_EXTERNAL_CASE_FACT
        weight = (
            self.weight_of(authority)
            * self.verification_multiplier(evidence.verification)
            * evidence.directness
            * evidence.reliability
            * evidence.relevance
            * evidence.strength
            * float(transferability)
        )
        return EvidenceGrade(
            evidence=evidence,
            authority_level=authority,
            effective_weight=weight,
            scope_gate="OK",
            reason=(
                f"transferability={transferability:.2f} >= {threshold}; "
                "eligible as external case fact (prior-only)."
            ),
        )

    # -- internals -----------------------------------------------------------

    def _default_authority(self, evidence: Evidence) -> AuthorityLevel:
        type_default = EVIDENCE_TYPE_TO_AUTHORITY.get(
            evidence.evidence_type.value
            if hasattr(evidence.evidence_type, "value")
            else str(evidence.evidence_type),
            AuthorityLevel.MODEL_PRIOR,
        )
        if evidence.authority_level not in (None, AuthorityLevel.MODEL_PRIOR.value):
            # Explicit authority already set by a capability. LLM-sourced
            # evidence may keep a self-report ONLY up to its type ceiling —
            # model output can never self-declare above LLM_INFERENCE /
            # MODEL_PRIOR. A self-report below the ceiling is honored.
            # (Non-LLM types ignore the self-report and fall back to the
            # type default, unchanged.)
            if evidence.evidence_type in (
                EvidenceType.LLM_INFERENCE.value,
                EvidenceType.MODEL_PRIOR.value,
            ):
                declared = AuthorityLevel(evidence.authority_level)
                if AUTHORITY_TABLE.get(declared.value, 0.10) > AUTHORITY_TABLE.get(
                    type_default.value, 0.10
                ):
                    return type_default
                return declared
        return type_default
