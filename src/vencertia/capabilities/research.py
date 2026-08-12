"""ResearchCapability — research planning + SearchProvider candidate evidence.

v1.1: upgraded to a ResearchRun facade: ResearchPlanner → Search → candidate
evidence (with provider call record + fingerprint metadata). The capability
still has NO write authority: it returns candidates only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import Evidence, ResearchPlan
from vencertia.domain.context import ContextBundle, ContextBundleV11
from vencertia.providers.models import SearchProvider
from vencertia.providers.search import SearchAdapter

if TYPE_CHECKING:
    from vencertia.runtime.research_planner import ResearchPlanner


class ResearchCapability:
    name = "research"

    def __init__(
        self,
        search: SearchProvider | None = None,
        planner: ResearchPlanner | None = None,
    ) -> None:
        self.search = search
        self.planner = planner
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

    def run_plan(
        self,
        decision,
        beliefs: list,
        criticals: list,
        context: ContextBundleV11 | None = None,
    ) -> ResearchPlan:
        """Run the planner and return a ResearchPlan (candidate only)."""
        if self.planner is None:
            from vencertia.runtime.research_planner import ResearchPlanner

            self.planner = ResearchPlanner()
        return self.planner.plan(decision, beliefs, criticals, context)

    def run_search(
        self,
        plan: ResearchPlan,
        question_index: int = 0,
        k: int = 2,
    ) -> list[Evidence]:
        """Execute one research question against the search provider."""
        if self.adapter is None or not plan.questions:
            return []
        question = plan.questions[question_index % len(plan.questions)]
        queries = question.search_queries or [question.question]
        candidates: list[Evidence] = []
        for query in queries[:2]:
            candidates.extend(
                self.adapter.to_candidate_evidence(
                    query=query, claim_ids=question.target_claim_ids, direction="SUPPORTS", k=k
                )
            )
        return candidates
