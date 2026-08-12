from __future__ import annotations

from pydantic import Field

from .models import MemoryType, NonEmptyStr, VencertiaBaseModel


PROFILE_MEMORY_TYPES = {
    MemoryType.FOUNDER_FACT,
    MemoryType.RESOURCE,
    MemoryType.CAPABILITY,
    MemoryType.CONSTRAINT,
    MemoryType.RED_LINE,
    MemoryType.PREFERENCE,
}


class FounderProfileRefreshRequest(VencertiaBaseModel):
    user_id: NonEmptyStr
    source_memory_ids: list[NonEmptyStr] = Field(default_factory=list)
    changed_memory_types: list[MemoryType] = Field(default_factory=list)
    reason: NonEmptyStr


def build_profile_refresh_request(user_id: str, changed_records) -> FounderProfileRefreshRequest | None:
    relevant = [r for r in changed_records if r.scope == "USER_GLOBAL" and r.memory_type in PROFILE_MEMORY_TYPES]
    if not relevant:
        return None
    return FounderProfileRefreshRequest(
        user_id=user_id,
        source_memory_ids=[r.memory_id for r in relevant],
        changed_memory_types=list(dict.fromkeys(r.memory_type for r in relevant)),
        reason="Durable Founder Memory changed; rebuild/synchronize canonical FounderProfile through the Founder domain service.",
    )
