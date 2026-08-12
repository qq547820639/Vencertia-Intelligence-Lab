from __future__ import annotations

from datetime import datetime, timezone
import re

from .models import (
    AccessClass,
    ConfidenceLevel,
    ImportanceLevel,
    MemoryRecord,
    MemoryRetrievalQuery,
    MemoryScope,
    MemoryStatus,
)
from .memory_repository import PersistedMemory


IMPORTANCE_SCORE = {
    ImportanceLevel.LOW: 1,
    ImportanceLevel.MEDIUM: 2,
    ImportanceLevel.HIGH: 3,
    ImportanceLevel.CRITICAL: 4,
}
CONFIDENCE_SCORE = {
    ConfidenceLevel.LOW: 1,
    ConfidenceLevel.MEDIUM: 2,
    ConfidenceLevel.HIGH: 3,
}


def _lexical_score(query: str | None, text: str) -> float:
    if not query:
        return 0.0
    q = {x for x in re.findall(r"[\w\u4e00-\u9fff]+", query.casefold()) if len(x) > 1}
    t = {x for x in re.findall(r"[\w\u4e00-\u9fff]+", text.casefold()) if len(x) > 1}
    if not q:
        return 0.0
    return len(q & t) / len(q)


def retrieve_memories(items: list[PersistedMemory], query: MemoryRetrievalQuery) -> list[PersistedMemory]:
    as_of = query.as_of or datetime.now(timezone.utc)
    allowed_access = {str(x) for x in query.access_classes}
    requested_types = {str(x) for x in query.memory_types}

    filtered: list[PersistedMemory] = []
    for item in items:
        r = item.record
        if r.user_id != query.user_id:
            continue
        if str(item.access_class) not in allowed_access:
            continue
        if r.status == MemoryStatus.ACTIVE:
            pass
        elif r.status == MemoryStatus.CONFLICTED and query.include_conflicted:
            pass
        elif query.include_historical and r.status in {MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED, MemoryStatus.EXPIRED}:
            pass
        else:
            continue
        if r.valid_from and r.valid_from > as_of:
            continue
        if r.valid_to and r.valid_to < as_of and not query.include_historical:
            continue
        if r.scope == MemoryScope.USER_GLOBAL:
            if not query.include_user_global:
                continue
        else:
            if not query.include_project_specific or r.project_id != query.project_id:
                continue
        if requested_types and str(r.memory_type) not in requested_types:
            continue
        filtered.append(item)

    def score(item: PersistedMemory):
        r = item.record
        critical = 1 if str(r.importance) == str(ImportanceLevel.CRITICAL) else 0
        # Critical constraints/red lines are intentionally favored.
        type_boost = 1 if str(r.memory_type) in {"RED_LINE", "CONSTRAINT", "EXCLUSION_RULE"} else 0
        return (
            critical,
            type_boost,
            IMPORTANCE_SCORE.get(ImportanceLevel(str(r.importance)), 0),
            CONFIDENCE_SCORE.get(ConfidenceLevel(str(r.confidence)), 0),
            _lexical_score(query.semantic_query, r.content),
            r.updated_at.timestamp(),
        )

    filtered.sort(key=score, reverse=True)
    return filtered[: query.max_results]
