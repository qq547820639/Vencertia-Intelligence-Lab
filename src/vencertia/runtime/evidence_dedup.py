"""EvidenceDedupEngine — fingerprint / canonical source / source family grouping.

Exact duplicates (same content fingerprint) are dropped and never persisted;
near-duplicates within the same source family share an ``independence_group``
so the BeliefEngine's existing correlation discount applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, Field

from vencertia.config import Settings, get_settings
from vencertia.domain import Evidence
from vencertia.providers.search import content_fingerprint


class DedupGroup(BaseModel):
    group_id: str
    canonical_evidence_id: str
    member_ids: list[str] = Field(default_factory=list)
    drop_reason: str = ""  # EXACT_FINGERPRINT | SAME_SOURCE_FAMILY | SIMILARITY
    independence_group: str = ""


class DedupResult(BaseModel):
    groups: list[DedupGroup] = Field(default_factory=list)
    dropped_ids: list[str] = Field(default_factory=list)
    kept_ids: list[str] = Field(default_factory=list)


@dataclass
class EvidenceDedupEngine:
    """Deterministic dedup over candidate evidence lists."""

    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()

    def fingerprint(self, evidence: Evidence) -> str:
        if evidence.content_fingerprint:
            return evidence.content_fingerprint
        # MAJOR-2 fix (QA): empty source must NOT fall back to the content hash
        # of "" — every empty-source evidence would share sha256("") and all but
        # the first would be silently dropped. Use a per-evidence unique key.
        if not (evidence.source or "").strip():
            return f"__unique__:{evidence.id}"
        return content_fingerprint(evidence.source)

    @staticmethod
    def canonical_source(evidence: Evidence) -> str:
        if evidence.canonical_source_id:
            return evidence.canonical_source_id
        url = (evidence.provenance.source_url or "") if evidence.provenance else ""
        if url:
            from vencertia.providers.search import canonical_source as cs

            return cs(url, str(evidence.source or ""))
        return (evidence.source or "").lower().strip()

    @staticmethod
    def source_family(evidence: Evidence) -> str:
        if evidence.source_family:
            return evidence.source_family
        url = (evidence.provenance.source_url or "") if evidence.provenance else ""
        if url:
            from vencertia.providers.search import source_family as sf

            return sf(url, str(evidence.source or ""))
        return "unknown_source"

    def group(self, evidence_list: list[Evidence]) -> DedupResult:
        groups: list[DedupGroup] = []
        dropped_ids: list[str] = []
        kept_ids: list[str] = []

        # 1) Exact fingerprint dedup.
        by_fingerprint: dict[str, list[Evidence]] = {}
        for evidence in evidence_list:
            by_fingerprint.setdefault(self.fingerprint(evidence), []).append(evidence)

        for _fp, items in by_fingerprint.items():
            items = sorted(items, key=lambda e: self._source_priority(e), reverse=True)
            canonical = items[0]
            members = items[1:]
            kept_ids.append(canonical.id)
            if members:
                dropped_ids.extend(m.id for m in members)
                groups.append(
                    DedupGroup(
                        group_id="DG_" + uuid4().hex,
                        canonical_evidence_id=canonical.id,
                        member_ids=[m.id for m in members],
                        drop_reason="EXACT_FINGERPRINT",
                        independence_group=canonical.id,
                    )
                )

        # 2) Same source family + high lexical similarity → shared independence group.
        from vencertia.runtime.claim_binding import lexical_overlap

        kept = [e for e in evidence_list if e.id in kept_ids]
        family_map: dict[str, list[Evidence]] = {}
        for evidence in kept:
            family_map.setdefault(self.source_family(evidence), []).append(evidence)

        for family, items in family_map.items():
            if len(items) < 2 or family == "unknown_source":
                continue
            items = sorted(items, key=lambda e: self._source_priority(e), reverse=True)
            canonical = items[0]
            # MAJOR-1 fix (QA): the canonical must also join the shared group so
            # the BeliefEngine keys canonical and members under the SAME group
            # id (canonical.id). Otherwise canonical key is
            # ``__unique__:<id>`` and members ``<id>`` → no correlation
            # discount (discounts stayed [1.0, 1.0] instead of [1.0, 0.5]).
            object.__setattr__(canonical, "independence_group", canonical.id)
            for other in items[1:]:
                overlap = lexical_overlap(canonical.source or "", other.source or "")
                if overlap >= self.settings.dedup_similarity_threshold:
                    if other.independence_group is None:
                        # Share the canonical's independence group so the belief
                        # engine discounts the near-duplicate.
                        object.__setattr__(other, "independence_group", canonical.id)
            groups.append(
                DedupGroup(
                    group_id="DG_" + uuid4().hex,
                    canonical_evidence_id=canonical.id,
                    member_ids=[o.id for o in items[1:]],
                    drop_reason="SAME_SOURCE_FAMILY",
                    independence_group=canonical.id,
                )
            )

        return DedupResult(
            groups=groups,
            dropped_ids=dropped_ids,
            kept_ids=kept_ids,
        )

    @staticmethod
    def _source_priority(evidence: Evidence) -> float:
        table = {
            "PROJECT_REALITY": 1.0,
            "PROJECT_DIRECT_BEHAVIOR": 0.95,
            "PROJECT_EXPERIMENT_RESULT": 0.9,
            "CUSTOMER_COMMITMENT_OR_PAYMENT": 0.88,
            "ELIGIBLE_EXTERNAL_CASE_FACT": 0.75,
            "REVIEWED_EXTERNAL_RESEARCH": 0.65,
            "FOUNDER_STATEMENT": 0.45,
            "LLM_INFERENCE": 0.2,
            "MODEL_PRIOR": 0.1,
        }
        key = evidence.authority_level.value if hasattr(evidence.authority_level, "value") else str(evidence.authority_level)
        return table.get(key, 0.1)
