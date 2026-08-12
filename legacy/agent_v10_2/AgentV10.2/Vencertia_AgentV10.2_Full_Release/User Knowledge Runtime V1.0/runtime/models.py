from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]


class VencertiaBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )


class ConfidenceLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ImportanceLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FactStatus(StrEnum):
    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    ASSUMED = "ASSUMED"
    UNKNOWN = "UNKNOWN"


class MemoryScope(StrEnum):
    USER_GLOBAL = "USER_GLOBAL"
    PROJECT_SPECIFIC = "PROJECT_SPECIFIC"


class MemoryType(StrEnum):
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


class MemoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONFLICTED = "CONFLICTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class SourceType(StrEnum):
    USER_EXPLICIT_INPUT = "USER_EXPLICIT_INPUT"
    USER_CORRECTION = "USER_CORRECTION"
    CUSTOMER_FEEDBACK = "CUSTOMER_FEEDBACK"
    EXPERIMENT_RESULT = "EXPERIMENT_RESULT"
    REAL_PAYMENT = "REAL_PAYMENT"
    PROJECT_DECISION = "PROJECT_DECISION"
    AGENT_INFERENCE = "AGENT_INFERENCE"
    DOCUMENT_CLAIM = "DOCUMENT_CLAIM"
    WEB_SOURCE = "WEB_SOURCE"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    TOOL_RESULT = "TOOL_RESULT"


class MemoryOperation(StrEnum):
    WRITE = "WRITE"
    MERGE = "MERGE"
    SUPERSEDE = "SUPERSEDE"
    CONFLICT = "CONFLICT"
    REJECT = "REJECT"
    EXPIRE = "EXPIRE"
    ARCHIVE = "ARCHIVE"


class ProperStore(StrEnum):
    STABLE_MEMORY = "STABLE_MEMORY"
    FOUNDER_PROFILE = "FOUNDER_PROFILE"
    PROJECT_KB = "PROJECT_KB"
    EVIDENCE_LEDGER = "EVIDENCE_LEDGER"
    ASSUMPTION_LEDGER = "ASSUMPTION_LEDGER"
    EXPERIMENT_LEDGER = "EXPERIMENT_LEDGER"
    ACTION_LEDGER = "ACTION_LEDGER"
    DECISION_LEDGER = "DECISION_LEDGER"
    FINANCIAL_SNAPSHOT = "FINANCIAL_SNAPSHOT"
    CUSTOMER_FEEDBACK = "CUSTOMER_FEEDBACK"
    STARTUP_INTELLIGENCE = "STARTUP_INTELLIGENCE"


class AccessClass(StrEnum):
    PRIVATE = "PRIVATE"
    INTERNAL = "INTERNAL"
    MATCHABLE = "MATCHABLE"
    PUBLIC = "PUBLIC"


class AgentId(StrEnum):
    A0_ORCHESTRATOR = "A0_ORCHESTRATOR"
    A1_FOUNDER_DIAGNOSIS = "A1_FOUNDER_DIAGNOSIS"
    A2_MARKET_OPPORTUNITY = "A2_MARKET_OPPORTUNITY"
    A3_VENTURE_DESIGN = "A3_VENTURE_DESIGN"
    A4_PROJECT_PROSECUTOR = "A4_PROJECT_PROSECUTOR"
    A5_FINANCIAL_BUSINESS_MODEL = "A5_FINANCIAL_BUSINESS_MODEL"
    A6_EXECUTION_STRATEGY = "A6_EXECUTION_STRATEGY"
    A7_NEXT_ACTION = "A7_NEXT_ACTION"
    A8_STARTUP_CASE_INTELLIGENCE = "A8_STARTUP_CASE_INTELLIGENCE"
    A9_FOUNDER_MATCHMAKING = "A9_FOUNDER_MATCHMAKING"
    A10_BUSINESS_PLAN = "A10_BUSINESS_PLAN"


class MemoryCandidate(VencertiaBaseModel):
    """Canonical AgentV10.1 durable-memory candidate DTO."""

    candidate_id: NonEmptyStr
    proposed_scope: MemoryScope
    proposed_memory_type: MemoryType
    content: NonEmptyStr
    structured_value: dict[str, Any] | None = None
    source_message_ids: list[NonEmptyStr] = Field(default_factory=list)
    source_entity_ids: list[NonEmptyStr] = Field(default_factory=list)
    fact_status: FactStatus = FactStatus.UNKNOWN
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    importance: ImportanceLevel = ImportanceLevel.MEDIUM
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    reason_to_remember: NonEmptyStr

    @model_validator(mode="after")
    def validate_time(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be >= valid_from")
        return self


class MemoryCandidateEnvelope(VencertiaBaseModel):
    """Runtime-only metadata around a canonical MemoryCandidate.

    This is intentionally not a new canonical knowledge entity.
    """

    candidate: MemoryCandidate
    source_types: list[SourceType] = Field(default_factory=list)
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)
    semantic_key: str | None = None
    proper_store: ProperStore = ProperStore.STABLE_MEMORY
    access_class: AccessClass = AccessClass.PRIVATE
    origin_agent: AgentId | None = None


class MemoryRecord(VencertiaBaseModel):
    """Canonical AgentV10.1 durable MemoryRecord."""

    memory_id: NonEmptyStr
    user_id: NonEmptyStr
    project_id: str | None = None
    scope: MemoryScope
    memory_type: MemoryType
    content: NonEmptyStr
    structured_value: dict[str, Any] | None = None
    source_message_ids: list[NonEmptyStr] = Field(default_factory=list)
    source_entity_ids: list[NonEmptyStr] = Field(default_factory=list)
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)
    fact_status: FactStatus
    confidence: ConfidenceLevel
    importance: ImportanceLevel
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_memory_id: str | None = None
    conflicts_with_memory_ids: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope_and_time(self):
        if self.scope == MemoryScope.PROJECT_SPECIFIC and not self.project_id:
            raise ValueError("PROJECT_SPECIFIC memory requires project_id")
        if self.scope == MemoryScope.USER_GLOBAL and self.project_id is not None:
            raise ValueError("USER_GLOBAL memory must have project_id=None; source project belongs in provenance")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be >= valid_from")
        return self


class MemoryPermission(VencertiaBaseModel):
    memory_id: NonEmptyStr
    user_id: NonEmptyStr
    access_class: AccessClass = AccessClass.PRIVATE
    updated_at: datetime


class MemoryConflict(VencertiaBaseModel):
    conflict_id: NonEmptyStr
    user_id: NonEmptyStr
    project_id: str | None = None
    semantic_key: str | None = None
    memory_ids: list[NonEmptyStr] = Field(min_length=2)
    reason: NonEmptyStr
    resolved: bool = False
    resolution_note: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class MemoryWriteRequest(VencertiaBaseModel):
    request_id: NonEmptyStr
    user_id: NonEmptyStr
    project_id: str | None = None
    candidates: list[MemoryCandidateEnvelope] = Field(min_length=1)
    idempotency_key: NonEmptyStr
    actor_id: NonEmptyStr


class MemoryWriteResult(VencertiaBaseModel):
    candidate_id: NonEmptyStr
    operation: MemoryOperation
    scope: MemoryScope
    project_id: str | None = None
    memory_type: MemoryType
    target_memory_id: str | None = None
    new_memory_record: MemoryRecord | None = None
    affected_memory_ids: list[NonEmptyStr] = Field(default_factory=list)
    reason: NonEmptyStr
    fact_status: FactStatus
    confidence: ConfidenceLevel
    importance: ImportanceLevel
    snapshot_refresh_required: bool = False
    context_index_refresh_required: bool = False


class RuntimeRefreshSignals(VencertiaBaseModel):
    founder_profile_refresh_required: bool = False
    project_snapshot_refresh_required: bool = False
    context_refresh_required: bool = False
    routing_reassessment_recommended: bool = False
    state_reassessment_recommended: bool = False


class MemoryWriteEvaluation(VencertiaBaseModel):
    request_id: NonEmptyStr
    user_id: NonEmptyStr
    project_id: str | None = None
    candidate_count: int = Field(ge=0)
    results: list[MemoryWriteResult] = Field(default_factory=list)
    conflicts_created: list[NonEmptyStr] = Field(default_factory=list)
    supersessions_created: list[NonEmptyStr] = Field(default_factory=list)
    rejected_candidates: list[NonEmptyStr] = Field(default_factory=list)
    snapshot_refresh_required: bool = False
    context_refresh_required: bool = False
    write_confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    runtime_refresh_signals: RuntimeRefreshSignals = Field(default_factory=RuntimeRefreshSignals)


class MemoryRetrievalQuery(VencertiaBaseModel):
    request_id: NonEmptyStr
    user_id: NonEmptyStr
    project_id: str | None = None
    semantic_query: str | None = None
    memory_types: list[MemoryType] = Field(default_factory=list)
    include_user_global: bool = True
    include_project_specific: bool = True
    include_conflicted: bool = True
    include_historical: bool = False
    access_classes: list[AccessClass] = Field(default_factory=lambda: [AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC])
    max_results: int = Field(default=30, ge=1, le=200)
    as_of: datetime | None = None

    @model_validator(mode="after")
    def validate_project_scope(self):
        if self.include_project_specific and self.project_id is None:
            # Project-specific retrieval is simply unavailable without a project; do not fail.
            self.include_project_specific = False
        return self


class ContextBuildRequest(VencertiaBaseModel):
    request_id: NonEmptyStr
    user_id: NonEmptyStr
    agent_id: AgentId
    task: NonEmptyStr
    project_id: str | None = None
    max_memory_records: int = Field(default=30, ge=1, le=100)
    token_budget: int = Field(default=6000, ge=500, le=50000)
    as_of: datetime | None = None


class ConflictAlert(VencertiaBaseModel):
    conflict_id: NonEmptyStr
    memory_ids: list[NonEmptyStr]
    reason: NonEmptyStr


class ContextBundle(VencertiaBaseModel):
    """Token-efficient task-specific projection for A0–A10.

    This is a DTO/read model, not a canonical truth store.
    """

    context_bundle_id: NonEmptyStr
    request_id: NonEmptyStr
    user_id: NonEmptyStr
    project_id: str | None = None
    agent_id: AgentId
    generated_at: datetime

    founder_profile: dict[str, Any] | None = None
    project_snapshot: dict[str, Any] | None = None
    founder_stable_memory: list[MemoryRecord] = Field(default_factory=list)
    current_stage: str | None = None
    current_bottleneck: str | None = None
    critical_assumptions: list[dict[str, Any]] = Field(default_factory=list)
    top_evidence: list[dict[str, Any]] = Field(default_factory=list)
    latest_experiments: list[dict[str, Any]] = Field(default_factory=list)
    latest_decisions: list[dict[str, Any]] = Field(default_factory=list)
    relevant_memories: list[MemoryRecord] = Field(default_factory=list)
    exclusion_rules: list[MemoryRecord] = Field(default_factory=list)
    conflict_alerts: list[ConflictAlert] = Field(default_factory=list)
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_notes: list[NonEmptyStr] = Field(default_factory=list)


class UserKnowledgeProjection(VencertiaBaseModel):
    """User-facing read projection. Never persist as an independent source of truth."""

    user_id: NonEmptyStr
    project_id: str | None = None
    generated_at: datetime
    founder_profile: dict[str, Any] | None = None
    global_memories: list[MemoryRecord] = Field(default_factory=list)
    project_memories: list[MemoryRecord] = Field(default_factory=list)
    unresolved_conflicts: list[MemoryConflict] = Field(default_factory=list)
    project_summaries: list[dict[str, Any]] = Field(default_factory=list)
    canonical_source_note: str = "Projection only; canonical data remains in FounderProfile, MemoryRecord, Project KB and domain ledgers."
