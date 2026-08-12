from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from .memory_permissions import DEFAULT_AGENT_ACCESS
from .memory_retrieval_policy import retrieve_memories
from .memory_repository import MemoryRepository
from .models import (
    AgentId,
    ConflictAlert,
    ContextBuildRequest,
    ContextBundle,
    MemoryRetrievalQuery,
    MemoryScope,
    MemoryType,
)


class ContextDataProvider(Protocol):
    """Integration boundary to canonical non-Memory stores already defined by AgentV10.1."""

    def get_founder_profile(self, user_id: str) -> dict[str, Any] | None: ...
    def get_project_snapshot(self, user_id: str, project_id: str | None) -> dict[str, Any] | None: ...
    def get_current_stage(self, user_id: str, project_id: str | None) -> str | None: ...
    def get_current_bottleneck(self, user_id: str, project_id: str | None) -> str | None: ...
    def get_critical_assumptions(self, user_id: str, project_id: str | None, limit: int = 5) -> list[dict[str, Any]]: ...
    def get_top_evidence(self, user_id: str, project_id: str | None, limit: int = 8) -> list[dict[str, Any]]: ...
    def get_latest_experiments(self, user_id: str, project_id: str | None, limit: int = 5) -> list[dict[str, Any]]: ...
    def get_latest_decisions(self, user_id: str, project_id: str | None, limit: int = 5) -> list[dict[str, Any]]: ...
    def get_recent_messages(self, user_id: str, project_id: str | None, limit: int = 8) -> list[dict[str, Any]]: ...
    def get_project_summaries(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]: ...


class NullContextDataProvider:
    def get_founder_profile(self, user_id): return None
    def get_project_snapshot(self, user_id, project_id): return None
    def get_current_stage(self, user_id, project_id): return None
    def get_current_bottleneck(self, user_id, project_id): return None
    def get_critical_assumptions(self, user_id, project_id, limit=5): return []
    def get_top_evidence(self, user_id, project_id, limit=8): return []
    def get_latest_experiments(self, user_id, project_id, limit=5): return []
    def get_latest_decisions(self, user_id, project_id, limit=5): return []
    def get_recent_messages(self, user_id, project_id, limit=8): return []
    def get_project_summaries(self, user_id, limit=20): return []


AGENT_MEMORY_TYPES = {
    AgentId.A0_ORCHESTRATOR: list(MemoryType),
    AgentId.A1_FOUNDER_DIAGNOSIS: [MemoryType.FOUNDER_FACT, MemoryType.CAPABILITY, MemoryType.RESOURCE, MemoryType.CONSTRAINT, MemoryType.PREFERENCE, MemoryType.RED_LINE, MemoryType.LESSON, MemoryType.EXCLUSION_RULE],
    AgentId.A2_MARKET_OPPORTUNITY: [MemoryType.CAPABILITY, MemoryType.RESOURCE, MemoryType.CONSTRAINT, MemoryType.PREFERENCE, MemoryType.RED_LINE, MemoryType.LESSON, MemoryType.EXCLUSION_RULE],
    AgentId.A3_VENTURE_DESIGN: [MemoryType.CAPABILITY, MemoryType.RESOURCE, MemoryType.CONSTRAINT, MemoryType.PREFERENCE, MemoryType.RED_LINE, MemoryType.PROJECT_DECISION, MemoryType.PIVOT_REASON, MemoryType.LESSON, MemoryType.EXCLUSION_RULE],
    AgentId.A4_PROJECT_PROSECUTOR: [MemoryType.CONSTRAINT, MemoryType.RED_LINE, MemoryType.RISK, MemoryType.PROJECT_DECISION, MemoryType.PIVOT_REASON, MemoryType.LESSON, MemoryType.EXCLUSION_RULE, MemoryType.ASSUMPTION, MemoryType.EVIDENCE],
    AgentId.A5_FINANCIAL_BUSINESS_MODEL: [MemoryType.CONSTRAINT, MemoryType.FINANCIAL_DATA, MemoryType.PROJECT_DECISION, MemoryType.RISK, MemoryType.LESSON, MemoryType.EVIDENCE, MemoryType.ASSUMPTION],
    AgentId.A6_EXECUTION_STRATEGY: [MemoryType.CAPABILITY, MemoryType.RESOURCE, MemoryType.CONSTRAINT, MemoryType.RED_LINE, MemoryType.PROJECT_DECISION, MemoryType.RISK, MemoryType.ACTION_RESULT, MemoryType.MILESTONE, MemoryType.LESSON],
    AgentId.A7_NEXT_ACTION: [MemoryType.RESOURCE, MemoryType.CONSTRAINT, MemoryType.RED_LINE, MemoryType.PROJECT_DECISION, MemoryType.RISK, MemoryType.ACTION_RESULT, MemoryType.MILESTONE, MemoryType.OPEN_QUESTION, MemoryType.EXPERIMENT_RESULT, MemoryType.LESSON],
    AgentId.A8_STARTUP_CASE_INTELLIGENCE: [MemoryType.PROJECT_FACT, MemoryType.RISK, MemoryType.PIVOT_REASON, MemoryType.LESSON],
    AgentId.A9_FOUNDER_MATCHMAKING: [MemoryType.FOUNDER_FACT, MemoryType.CAPABILITY, MemoryType.RESOURCE, MemoryType.PREFERENCE],
    AgentId.A10_BUSINESS_PLAN: [MemoryType.PROJECT_FACT, MemoryType.PROJECT_DECISION, MemoryType.FINANCIAL_DATA, MemoryType.RISK, MemoryType.MILESTONE, MemoryType.ASSUMPTION, MemoryType.EVIDENCE, MemoryType.LESSON],
}


class ContextBuilder:
    def __init__(self, repository: MemoryRepository, data_provider: ContextDataProvider | None = None):
        self.repository = repository
        self.data_provider = data_provider or NullContextDataProvider()

    def build(self, request: ContextBuildRequest) -> ContextBundle:
        query = MemoryRetrievalQuery(
            request_id=request.request_id,
            user_id=request.user_id,
            project_id=request.project_id,
            semantic_query=request.task,
            memory_types=AGENT_MEMORY_TYPES[request.agent_id],
            include_user_global=True,
            include_project_specific=request.project_id is not None,
            include_conflicted=True,
            include_historical=False,
            access_classes=list(DEFAULT_AGENT_ACCESS[request.agent_id]),
            max_results=request.max_memory_records,
            as_of=request.as_of,
        )
        selected = retrieve_memories(self.repository.list_for_user(request.user_id), query)
        global_mem = [x.record for x in selected if x.record.scope == MemoryScope.USER_GLOBAL]
        project_mem = [x.record for x in selected if x.record.scope == MemoryScope.PROJECT_SPECIFIC]
        exclusions = [x.record for x in selected if x.record.memory_type == MemoryType.EXCLUSION_RULE]

        alerts = []
        for conflict in self.repository.list_conflicts(request.user_id, request.project_id, unresolved_only=True):
            if any(mid in {m.memory_id for m in global_mem + project_mem} for mid in conflict.memory_ids):
                alerts.append(ConflictAlert(conflict_id=conflict.conflict_id, memory_ids=conflict.memory_ids, reason=conflict.reason))

        notes = [
            "ContextBundle is a read projection, not a canonical source of truth.",
            "ACTIVE durable Memory is preferred; conflicts are explicit and never silently averaged.",
        ]
        if request.agent_id == AgentId.A8_STARTUP_CASE_INTELLIGENCE:
            notes.append("Do not export raw private User Memory to external research tools; derive a minimum privacy-safe case query.")
        if request.agent_id == AgentId.A9_FOUNDER_MATCHMAKING:
            notes.append("Only MATCHABLE/PUBLIC Memory is included; never expose full private Founder Memory.")
        if request.agent_id == AgentId.A5_FINANCIAL_BUSINESS_MODEL:
            notes.append("Current financial metrics come from the latest Financial Snapshot; Memory is supplementary durable context.")

        return ContextBundle(
            context_bundle_id=f"CTX_{uuid4().hex}",
            request_id=request.request_id,
            user_id=request.user_id,
            project_id=request.project_id,
            agent_id=request.agent_id,
            generated_at=datetime.now(timezone.utc),
            founder_profile=self.data_provider.get_founder_profile(request.user_id),
            project_snapshot=self.data_provider.get_project_snapshot(request.user_id, request.project_id),
            founder_stable_memory=global_mem,
            current_stage=self.data_provider.get_current_stage(request.user_id, request.project_id),
            current_bottleneck=self.data_provider.get_current_bottleneck(request.user_id, request.project_id),
            critical_assumptions=self.data_provider.get_critical_assumptions(request.user_id, request.project_id, 5),
            top_evidence=self.data_provider.get_top_evidence(request.user_id, request.project_id, 8),
            latest_experiments=self.data_provider.get_latest_experiments(request.user_id, request.project_id, 5),
            latest_decisions=self.data_provider.get_latest_decisions(request.user_id, request.project_id, 5),
            relevant_memories=project_mem,
            exclusion_rules=exclusions,
            conflict_alerts=alerts,
            recent_messages=self.data_provider.get_recent_messages(request.user_id, request.project_id, 8),
            retrieval_notes=notes,
        )
