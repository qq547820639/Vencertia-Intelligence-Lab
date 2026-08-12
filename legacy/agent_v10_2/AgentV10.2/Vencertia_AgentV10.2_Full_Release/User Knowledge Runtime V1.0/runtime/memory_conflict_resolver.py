from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from .memory_deduplicator import exact_duplicate
from .models import MemoryCandidateEnvelope, MemoryRecord, SourceType


class SemanticRelation(StrEnum):
    EQUIVALENT = "EQUIVALENT"
    DETAIL_EXTENSION = "DETAIL_EXTENSION"
    TEMPORAL_UPDATE = "TEMPORAL_UPDATE"
    CONFLICT = "CONFLICT"
    DISTINCT = "DISTINCT"
    UNSURE = "UNSURE"


class SemanticAdjudicator(Protocol):
    def adjudicate(self, candidate: MemoryCandidateEnvelope, existing: MemoryRecord) -> SemanticRelation:
        ...


class ConservativeSemanticAdjudicator:
    """Safe deterministic fallback.

    Production may replace this with an LLM-backed semantic adjudicator. The LLM decides
    semantic meaning; code still owns authorization, project/tenant checks and persistence.
    """

    def adjudicate(self, candidate: MemoryCandidateEnvelope, existing: MemoryRecord) -> SemanticRelation:
        c = candidate.candidate
        if exact_duplicate(c, existing):
            return SemanticRelation.EQUIVALENT

        if candidate.semantic_key is None:
            return SemanticRelation.DISTINCT

        if SourceType.USER_CORRECTION in candidate.source_types:
            return SemanticRelation.TEMPORAL_UPDATE

        if c.valid_from and existing.valid_from and c.valid_from > existing.valid_from:
            return SemanticRelation.TEMPORAL_UPDATE

        only_inference = bool(candidate.source_types) and all(
            s == SourceType.AGENT_INFERENCE for s in candidate.source_types
        )
        if only_inference and existing.fact_status == "VERIFIED":
            return SemanticRelation.UNSURE

        # Same declared semantic key + incompatible content is conservatively a conflict.
        return SemanticRelation.CONFLICT
