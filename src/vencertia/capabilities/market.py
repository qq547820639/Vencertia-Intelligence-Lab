"""MarketCapability — market/category research candidate evidence."""

from __future__ import annotations

from uuid import uuid4

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import Direction, Evidence, EvidenceType, Scope
from vencertia.runtime.context import ContextBundle


class MarketCapability:
    name = "market"

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        claim_ids = [b.claim_id for b in context.critical_assumptions]
        evidence = [
            Evidence(
                id=f"E_{uuid4().hex}",
                claim_ids=claim_ids,
                scope=Scope.MARKET,
                evidence_type=EvidenceType.REVIEWED_EXTERNAL_RESEARCH.value,
                source="Market capability (mock): category is growing but fragmented.",
                directness=0.5,
                reliability=0.6,
                relevance=0.5,
                strength=0.4,
                supports_or_contradicts=Direction.SUPPORTS.value,
                authority_level="REVIEWED_EXTERNAL_RESEARCH",
                verification="ESTIMATED",
            )
        ]
        return CapabilityResult(
            evidence=evidence,
            notes=["Candidate market evidence only."],
        )
