"""SearchAdapter — converts SearchProvider results into candidate evidence.

Candidate authority is REVIEWED_EXTERNAL_RESEARCH (verified external research)
or LLM_INFERENCE; candidates are never VERIFIED by construction.

v1.1: outputs also carry ``content_fingerprint``, ``canonical_source_id`` and
``source_family`` so the EvidenceDedupEngine can group them offline.
"""

from __future__ import annotations

import hashlib
import re
from uuid import uuid4

from vencertia.domain import Direction, Evidence, Scope, utcnow
from vencertia.providers.models import SearchProvider

_FINGERPRINT_RE = re.compile(r"[\W_]+", re.UNICODE)


def content_fingerprint(text: str) -> str:
    """sha256 of the normalized text (lowercase, punctuation stripped)."""
    normalized = _FINGERPRINT_RE.sub(" ", text.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_source(url: str, source: str = "") -> str:
    """Normalize a source to a canonical id (URL host+path, else source name)."""
    if url:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.netloc:
            return f"{parsed.netloc}{parsed.path}".rstrip("/").lower()
    return (source or "unknown_source").lower().strip()


def source_family(url: str, source: str = "") -> str:
    """Return the media family for a source (registrable domain or source name)."""
    if url:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        parts = host.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return host
    return (source or "unknown_source").lower().strip()


class SearchAdapter:
    """Turns search results into candidate Evidence records."""

    def __init__(self, search: SearchProvider, authority: str = "REVIEWED_EXTERNAL_RESEARCH") -> None:
        self.search = search
        self.authority = authority

    def to_candidate_evidence(
        self,
        query: str,
        claim_ids: list[str],
        direction: str = Direction.SUPPORTS.value,
        k: int = 5,
    ) -> list[Evidence]:
        results = self.search.search(query, k=k)
        candidates: list[Evidence] = []
        for _index, result in enumerate(results):
            source_text = result.title + " — " + result.snippet
            candidates.append(
                Evidence(
                    id=f"E_{uuid4().hex}",
                    claim_ids=list(claim_ids),
                    scope=Scope.MARKET,
                    evidence_type="REVIEWED_EXTERNAL_RESEARCH",
                    provenance={"source_url": result.url, "tool": "SearchAdapter", "raw_extract": result.snippet},
                    source=source_text,
                    directness=0.6,
                    reliability=0.6,
                    relevance=0.6,
                    strength=0.5,
                    supports_or_contradicts=direction,
                    independence_group=f"search:{query}",
                    observed_at=result.retrieved_at or utcnow(),
                    authority_level=self.authority,
                    verification="ESTIMATED",
                    content_fingerprint=content_fingerprint(source_text),
                    canonical_source_id=canonical_source(result.url, result.source),
                    source_family=source_family(result.url, result.source),
                )
            )
        return candidates
