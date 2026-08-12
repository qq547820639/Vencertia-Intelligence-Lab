from __future__ import annotations

from .models import (
    FactStatus,
    MemoryCandidateEnvelope,
    MemoryType,
    ProperStore,
    SourceType,
)


FOUNDER_PROFILE_AFFECTING_TYPES = {
    MemoryType.FOUNDER_FACT,
    MemoryType.RESOURCE,
    MemoryType.CAPABILITY,
    MemoryType.CONSTRAINT,
    MemoryType.RED_LINE,
    MemoryType.PREFERENCE,
}

PROJECT_SNAPSHOT_AFFECTING_TYPES = {
    MemoryType.PROJECT_FACT,
    MemoryType.PROJECT_DECISION,
    MemoryType.RISK,
    MemoryType.MILESTONE,
    MemoryType.PIVOT_REASON,
    MemoryType.EXCLUSION_RULE,
}


def validate_candidate_authority(envelope: MemoryCandidateEnvelope) -> str | None:
    c = envelope.candidate

    if envelope.proper_store != ProperStore.STABLE_MEMORY:
        return f"Candidate belongs in {envelope.proper_store}, not Stable Memory."

    only_agent_inference = bool(envelope.source_types) and all(
        s == SourceType.AGENT_INFERENCE for s in envelope.source_types
    )
    if only_agent_inference and c.fact_status == FactStatus.VERIFIED and not envelope.evidence_ids:
        return "Agent inference without supporting evidence cannot become VERIFIED durable Memory."

    if c.proposed_memory_type == MemoryType.FINANCIAL_DATA and envelope.proper_store == ProperStore.FINANCIAL_SNAPSHOT:
        return "Current financial metric belongs in versioned Financial Snapshot."

    return None


def requires_founder_profile_refresh(envelope: MemoryCandidateEnvelope) -> bool:
    return envelope.candidate.proposed_memory_type in FOUNDER_PROFILE_AFFECTING_TYPES


def requires_project_snapshot_refresh(envelope: MemoryCandidateEnvelope) -> bool:
    return envelope.candidate.proposed_memory_type in PROJECT_SNAPSHOT_AFFECTING_TYPES
