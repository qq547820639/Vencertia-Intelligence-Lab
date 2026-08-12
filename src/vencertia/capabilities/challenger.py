"""ChallengerCapability — counter-evidence / devil's advocate candidates."""

from __future__ import annotations

from uuid import uuid4

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import Direction, Evidence, EvidenceType, Scope
from vencertia.runtime.context import ContextBundle


class ChallengerCapability:
    name = "challenger"

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        claim_ids = [b.claim_id for b in context.critical_assumptions]
        evidence = [
            Evidence(
                id=f"E_{uuid4().hex}",
                claim_ids=claim_ids,
                scope=Scope.PROJECT,
                evidence_type=EvidenceType.LLM_INFERENCE.value,
                source="Challenger capability (mock): interviews may overstate willingness to pay.",
                directness=0.4,
                reliability=0.5,
                relevance=0.8,
                strength=0.4,
                supports_or_contradicts=Direction.CONTRADICTS.value,
                authority_level="LLM_INFERENCE",
                verification="UNKNOWN",
            )
        ]
        return CapabilityResult(
            evidence=evidence,
            notes=["Adversarial candidate; triggers conflict detection."],
        )
