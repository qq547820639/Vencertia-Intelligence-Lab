from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Protocol

from .models import AccessClass, MemoryConflict, MemoryRecord, MemoryStatus, SourceType


@dataclass
class PersistedMemory:
    record: MemoryRecord
    semantic_key: str | None = None
    source_types: set[SourceType] = field(default_factory=set)
    access_class: AccessClass = AccessClass.PRIVATE
    row_version: int = 1


class MemoryRepository(Protocol):
    def get(self, memory_id: str) -> PersistedMemory | None: ...
    def list_for_user(self, user_id: str) -> list[PersistedMemory]: ...
    def find_semantic_family(self, user_id: str, project_id: str | None, semantic_key: str | None, memory_type: str, content: str) -> list[PersistedMemory]: ...
    def upsert(self, item: PersistedMemory) -> None: ...
    def add_conflict(self, conflict: MemoryConflict) -> None: ...
    def list_conflicts(self, user_id: str, project_id: str | None = None, unresolved_only: bool = True) -> list[MemoryConflict]: ...
    def save_idempotent_result(self, user_id: str, idempotency_key: str, candidate_id: str, result: object) -> None: ...
    def load_idempotent_result(self, user_id: str, idempotency_key: str, candidate_id: str) -> object | None: ...


class InMemoryMemoryRepository:
    def __init__(self):
        self.memories: dict[str, PersistedMemory] = {}
        self.conflicts: dict[str, MemoryConflict] = {}
        self.idempotency: dict[tuple[str, str, str], object] = {}

    def get(self, memory_id: str) -> PersistedMemory | None:
        return self.memories.get(memory_id)

    def list_for_user(self, user_id: str) -> list[PersistedMemory]:
        return [m for m in self.memories.values() if m.record.user_id == user_id]

    def find_semantic_family(self, user_id: str, project_id: str | None, semantic_key: str | None, memory_type: str, content: str) -> list[PersistedMemory]:
        from .memory_deduplicator import normalize_text
        out = []
        for item in self.memories.values():
            r = item.record
            if r.user_id != user_id or str(r.memory_type) != str(memory_type):
                continue
            if r.project_id != project_id:
                continue
            if r.status not in {MemoryStatus.ACTIVE, MemoryStatus.CONFLICTED}:
                continue
            if semantic_key is not None:
                if item.semantic_key == semantic_key:
                    out.append(item)
            elif normalize_text(r.content) == normalize_text(content):
                out.append(item)
        return sorted(out, key=lambda x: x.record.updated_at, reverse=True)

    def upsert(self, item: PersistedMemory) -> None:
        prior = self.memories.get(item.record.memory_id)
        if prior is not None:
            item.row_version = prior.row_version + 1
        self.memories[item.record.memory_id] = item

    def add_conflict(self, conflict: MemoryConflict) -> None:
        self.conflicts[conflict.conflict_id] = conflict

    def list_conflicts(self, user_id: str, project_id: str | None = None, unresolved_only: bool = True) -> list[MemoryConflict]:
        result = []
        for c in self.conflicts.values():
            if c.user_id != user_id:
                continue
            if project_id is not None and c.project_id != project_id:
                continue
            if unresolved_only and c.resolved:
                continue
            result.append(c)
        return result

    def save_idempotent_result(self, user_id: str, idempotency_key: str, candidate_id: str, result: object) -> None:
        self.idempotency[(user_id, idempotency_key, candidate_id)] = result

    def load_idempotent_result(self, user_id: str, idempotency_key: str, candidate_id: str) -> object | None:
        return self.idempotency.get((user_id, idempotency_key, candidate_id))
