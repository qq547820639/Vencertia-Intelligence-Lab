"""SearchAdapter — converts SearchProvider results into candidate evidence.

Candidate authority is REVIEWED_EXTERNAL_RESEARCH (verified external research)
or LLM_INFERENCE; candidates are never VERIFIED by construction.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from vencertia.domain import Direction, Evidence, Scope, utcnow
from vencertia.providers.models import SearchProvider, SearchResult


class SearchAdapter:
    """Turns search results into candidate Evidence records."""

    def __init__(self, search: SearchProvider, authority: str = "REVIEWED_EXTERNAL_RESEARCH") -> None:
        self.search = search
        self.authority = authority

    def to_candidate_evidence(
        self,
        query: str,
        claim_ids: List[str],
        direction: str = Direction.SUPPORTS.value,
        k: int = 5,
    ) -> List[Evidence]:
        results = self.search.search(query, k=k)
        candidates: List[Evidence] = []
        for index, result in enumerate(results):
            candidates.append(
                Evidence(
                    id=f"E_{uuid4().hex}",
                    claim_ids=list(claim_ids),
                    scope=Scope.MARKET,
                    evidence_type="REVIEWED_EXTERNAL_RESEARCH",
                    provenance={"source_url": result.url, "tool": "SearchAdapter", "raw_extract": result.snippet},
                    source=result.title + " — " + result.snippet,
                    directness=0.6,
                    reliability=0.6,
                    relevance=0.6,
                    strength=0.5,
                    supports_or_contradicts=direction,
                    independence_group=f"search:{query}",
                    observed_at=result.retrieved_at or utcnow(),
                    authority_level=self.authority,
                    verification="ESTIMATED",
                )
            )
        return candidates
