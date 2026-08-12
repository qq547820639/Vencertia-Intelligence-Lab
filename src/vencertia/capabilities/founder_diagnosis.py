"""FounderDiagnosisCapability — candidate FounderState features from memory."""

from __future__ import annotations

from uuid import uuid4

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import Direction, Evidence, EvidenceType, Scope
from vencertia.domain.context import ContextBundle


class FounderDiagnosisCapability:
    name = "founder_diagnosis"

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        evidence: list[Evidence] = []
        founder = context.founder_profile
        if founder is not None:
            evidence.append(
                Evidence(
                    id=f"E_{uuid4().hex}",
                    claim_ids=[],
                    scope=Scope.FOUNDER,
                    evidence_type=EvidenceType.FOUNDER_STATEMENT.value,
                    source=(
                        f"Founder profile snapshot: sales_ability={founder.sales_ability}, "
                        f"network={founder.network}, risk_tolerance={founder.risk_tolerance}."
                    ),
                    directness=0.9,
                    reliability=0.7,
                    relevance=0.8,
                    strength=0.6,
                    supports_or_contradicts=Direction.NEUTRAL.value,
                    authority_level="FOUNDER_STATEMENT",
                    verification="ESTIMATED",
                )
            )
        return CapabilityResult(
            evidence=evidence,
            notes=["Candidate founder state features; no write to FounderProfile."],
        )
