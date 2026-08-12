"""Memory domain — inherited verbatim from V10.2 User Knowledge Runtime.

Field semantics preserved: MemoryScope/MemoryType/MemoryStatus/MemoryOperation/
AccessClass enums plus MemoryRecord/MemoryCandidate objects.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, Verification, utcnow


class MemoryScope(str, Enum):
    USER_GLOBAL = "USER_GLOBAL"
    PROJECT_SPECIFIC = "PROJECT_SPECIFIC"


class MemoryType(str, Enum):
    FOUNDER_FACT = "FOUNDER_FACT"
    RESOURCE = "RESOURCE"
    CAPABILITY = "CAPABILITY"
    CONSTRAINT = "CONSTRAINT"
    RED_LINE = "RED_LINE"
    PREFERENCE = "PREFERENCE"
    PROJECT_FACT = "PROJECT_FACT"
    PROJECT_DECISION = "PROJECT_DECISION"
    ASSUMPTION = "ASSUMPTION"
    EVIDENCE = "EVIDENCE"
    CUSTOMER_FEEDBACK = "CUSTOMER_FEEDBACK"
    EXPERIMENT_RESULT = "EXPERIMENT_RESULT"
    FINANCIAL_DATA = "FINANCIAL_DATA"
    RISK = "RISK"
    ACTION = "ACTION"
    ACTION_RESULT = "ACTION_RESULT"
    MILESTONE = "MILESTONE"
    OPEN_QUESTION = "OPEN_QUESTION"
    EXCLUSION_RULE = "EXCLUSION_RULE"
    PIVOT_REASON = "PIVOT_REASON"
    LESSON = "LESSON"


class MemoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONFLICTED = "CONFLICTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class MemoryOperation(str, Enum):
    WRITE = "WRITE"
    MERGE = "MERGE"
    SUPERSEDE = "SUPERSEDE"
    CONFLICT = "CONFLICT"
    REJECT = "REJECT"
    EXPIRE = "EXPIRE"
    ARCHIVE = "ARCHIVE"


class AccessClass(str, Enum):
    PRIVATE = "PRIVATE"
    INTERNAL = "INTERNAL"
    MATCHABLE = "MATCHABLE"
    PUBLIC = "PUBLIC"


class MemoryRecord(VencertiaBaseModel):
    """Durable memory record (V10.2 contract, fields preserved)."""

    memory_id: str  # M_...
    user_id: str
    project_id: str | None = None
    scope: MemoryScope
    memory_type: MemoryType
    content: str
    structured_value: dict | None = None
    source_message_ids: list[str] = Field(default_factory=list)
    source_entity_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    fact_status: Verification = Verification.UNKNOWN
    confidence: str = "MEDIUM"  # LOW | MEDIUM | HIGH
    importance: str = "MEDIUM"  # LOW | MEDIUM | HIGH | CRITICAL
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_memory_id: str | None = None
    conflicts_with_memory_ids: list[str] = Field(default_factory=list)
    version: int = 1

    @property
    def id(self) -> str:
        """Alias so the generic repository can address this entity."""
        return self.memory_id


class MemoryCandidate(VencertiaBaseModel):
    candidate_id: str
    proposed_scope: MemoryScope
    proposed_memory_type: MemoryType
    content: str
    structured_value: dict | None = None
    source_types: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    fact_status: Verification = Verification.UNKNOWN
    confidence: str = "MEDIUM"
    importance: str = "MEDIUM"
    semantic_key: str | None = None
    access_class: AccessClass = AccessClass.PRIVATE
    proper_store: str = "STABLE_MEMORY"
