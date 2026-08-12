"""ResearchCapability — research planning + SearchProvider candidate evidence."""

from __future__ import annotations

from vencertia.capabilities.base import CapabilityResult
from vencertia.providers.models import SearchProvider
from vencertia.providers.search import SearchAdapter
from vencertia.runtime.context import ContextBundle


class ResearchCapability:
    name = "research"

    def __init__(self, search: SearchProvider | None = None) -> None:
        self.search = search
        self.adapter = SearchAdapter(search) if search is not None else None

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        if self.adapter is None:
            return CapabilityResult(notes=["No SearchProvider configured; no research evidence."])
        claim_ids = [b.claim_id for b in context.critical_assumptions]
        evidence = self.adapter.to_candidate_evidence(
            query=task,
            claim_ids=claim_ids,
            direction="SUPPORTS",
            k=3,
        )
        return CapabilityResult(
            evidence=evidence,
            notes=[f"Research capability produced {len(evidence)} candidate evidence items."],
        )
