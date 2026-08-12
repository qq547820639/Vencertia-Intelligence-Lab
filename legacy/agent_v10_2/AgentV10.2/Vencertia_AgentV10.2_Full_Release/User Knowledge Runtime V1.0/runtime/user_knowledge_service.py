from __future__ import annotations

from datetime import datetime, timezone

from .context_builder import ContextBuilder, ContextDataProvider, NullContextDataProvider
from .memory_manager import MemoryManager
from .memory_repository import MemoryRepository
from .memory_retrieval_policy import retrieve_memories
from .models import (
    AccessClass,
    ContextBuildRequest,
    ContextBundle,
    MemoryRetrievalQuery,
    MemoryScope,
    MemoryWriteEvaluation,
    MemoryWriteRequest,
    UserKnowledgeProjection,
)


class UserKnowledgeService:
    """Facade that makes the distributed AgentV10.1 stores feel like one user knowledge system.

    It never writes a second generic `KnowledgeRecord`.
    """

    def __init__(self, repository: MemoryRepository, data_provider: ContextDataProvider | None = None):
        self.repository = repository
        self.data_provider = data_provider or NullContextDataProvider()
        self.memory_manager = MemoryManager(repository)
        self.context_builder = ContextBuilder(repository, self.data_provider)

    def write_memory(self, request: MemoryWriteRequest) -> MemoryWriteEvaluation:
        return self.memory_manager.write(request)

    def build_agent_context(self, request: ContextBuildRequest) -> ContextBundle:
        return self.context_builder.build(request)

    def get_user_knowledge_projection(self, user_id: str, project_id: str | None = None) -> UserKnowledgeProjection:
        q = MemoryRetrievalQuery(
            request_id="USER_KNOWLEDGE_VIEW",
            user_id=user_id,
            project_id=project_id,
            include_user_global=True,
            include_project_specific=project_id is not None,
            include_conflicted=True,
            include_historical=False,
            access_classes=[AccessClass.PRIVATE, AccessClass.INTERNAL, AccessClass.MATCHABLE, AccessClass.PUBLIC],
            max_results=200,
        )
        items = retrieve_memories(self.repository.list_for_user(user_id), q)
        return UserKnowledgeProjection(
            user_id=user_id,
            project_id=project_id,
            generated_at=datetime.now(timezone.utc),
            founder_profile=self.data_provider.get_founder_profile(user_id),
            global_memories=[x.record for x in items if x.record.scope == MemoryScope.USER_GLOBAL],
            project_memories=[x.record for x in items if x.record.scope == MemoryScope.PROJECT_SPECIFIC],
            unresolved_conflicts=self.repository.list_conflicts(user_id, project_id, unresolved_only=True),
            project_summaries=self.data_provider.get_project_summaries(user_id, 20),
        )
