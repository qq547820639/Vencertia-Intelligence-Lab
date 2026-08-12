from runtime.memory_repository import InMemoryMemoryRepository
from runtime.user_knowledge_service import UserKnowledgeService
from runtime.models import (
    AccessClass, AgentId, ConfidenceLevel, ContextBuildRequest, FactStatus,
    ImportanceLevel, MemoryCandidate, MemoryCandidateEnvelope, MemoryScope,
    MemoryType, MemoryWriteRequest, SourceType,
)

repo = InMemoryMemoryRepository()
service = UserKnowledgeService(repo)

# A1 / user interaction creates durable Founder candidates.
write = service.write_memory(MemoryWriteRequest(
    request_id="REQ_A1_001",
    user_id="U001",
    candidates=[
        MemoryCandidateEnvelope(
            candidate=MemoryCandidate(
                candidate_id="C_TIME",
                proposed_scope=MemoryScope.USER_GLOBAL,
                proposed_memory_type=MemoryType.CONSTRAINT,
                content="Founder can allocate about 10 hours per week.",
                structured_value={"hours_per_week": 10},
                source_message_ids=["MSG_101"],
                fact_status=FactStatus.VERIFIED,
                confidence=ConfidenceLevel.HIGH,
                importance=ImportanceLevel.CRITICAL,
                reason_to_remember="Future venture design must fit Founder capacity.",
            ),
            source_types=[SourceType.USER_EXPLICIT_INPUT],
            semantic_key="founder.available_time",
            access_class=AccessClass.PRIVATE,
            origin_agent=AgentId.A1_FOUNDER_DIAGNOSIS,
        ),
        MemoryCandidateEnvelope(
            candidate=MemoryCandidate(
                candidate_id="C_REDLINE",
                proposed_scope=MemoryScope.USER_GLOBAL,
                proposed_memory_type=MemoryType.RED_LINE,
                content="Founder refuses businesses requiring personal livestreaming.",
                source_message_ids=["MSG_102"],
                fact_status=FactStatus.VERIFIED,
                confidence=ConfidenceLevel.HIGH,
                importance=ImportanceLevel.CRITICAL,
                reason_to_remember="This is a durable entrepreneurship red line.",
            ),
            source_types=[SourceType.USER_EXPLICIT_INPUT],
            semantic_key="founder.red_line.personal_livestreaming",
            access_class=AccessClass.PRIVATE,
            origin_agent=AgentId.A1_FOUNDER_DIAGNOSIS,
        ),
    ],
    idempotency_key="A1_TURN_001",
    actor_id="A1_FOUNDER_DIAGNOSIS",
))

# Later A3 gets a curated ContextBundle rather than the full chat history.
context = service.build_agent_context(ContextBuildRequest(
    request_id="REQ_A3_001",
    user_id="U001",
    agent_id=AgentId.A3_VENTURE_DESIGN,
    task="Design exactly three venture projects for this Founder.",
))

print(write.model_dump_json(indent=2))
print(context.model_dump_json(indent=2))
