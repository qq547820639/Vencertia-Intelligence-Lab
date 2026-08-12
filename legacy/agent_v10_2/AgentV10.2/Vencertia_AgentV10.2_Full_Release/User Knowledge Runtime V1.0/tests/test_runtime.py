from datetime import datetime, timedelta, timezone

import pytest

from runtime.context_builder import ContextBuilder
from runtime.memory_manager import MemoryManager
from runtime.memory_repository import InMemoryMemoryRepository, PersistedMemory
from runtime.memory_retrieval_policy import retrieve_memories
from runtime.models import (
    AccessClass,
    AgentId,
    ConfidenceLevel,
    ContextBuildRequest,
    FactStatus,
    ImportanceLevel,
    MemoryCandidate,
    MemoryCandidateEnvelope,
    MemoryOperation,
    MemoryRecord,
    MemoryRetrievalQuery,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    MemoryWriteRequest,
    ProperStore,
    SourceType,
)

NOW = datetime.now(timezone.utc)


def cand(cid="C1", scope=MemoryScope.USER_GLOBAL, typ=MemoryType.CONSTRAINT, content="Founder can allocate 8 hours/week.", value=None, source=SourceType.USER_EXPLICIT_INPUT, fact=FactStatus.VERIFIED, valid_from=None, store=ProperStore.STABLE_MEMORY, access=AccessClass.PRIVATE, key="founder.available_time"):
    return MemoryCandidateEnvelope(
        candidate=MemoryCandidate(
            candidate_id=cid,
            proposed_scope=scope,
            proposed_memory_type=typ,
            content=content,
            structured_value=value,
            source_message_ids=[f"MSG_{cid}"],
            fact_status=fact,
            confidence=ConfidenceLevel.HIGH,
            importance=ImportanceLevel.HIGH,
            valid_from=valid_from,
            reason_to_remember="Changes future venture decisions.",
        ),
        source_types=[source],
        semantic_key=key,
        proper_store=store,
        access_class=access,
    )


def write(manager, env, project_id=None, idem="I1"):
    return manager.write(MemoryWriteRequest(
        request_id=f"REQ_{env.candidate.candidate_id}",
        user_id="U1",
        project_id=project_id,
        candidates=[env],
        idempotency_key=idem,
        actor_id="TEST",
    ))


def test_canonical_memory_enums_exact():
    assert {x.value for x in MemoryStatus} == {"ACTIVE","SUPERSEDED","CONFLICTED","REJECTED","EXPIRED","ARCHIVED"}
    assert {x.value for x in MemoryType} == {
        "FOUNDER_FACT","RESOURCE","CAPABILITY","CONSTRAINT","RED_LINE","PREFERENCE",
        "PROJECT_FACT","PROJECT_DECISION","ASSUMPTION","EVIDENCE","CUSTOMER_FEEDBACK",
        "EXPERIMENT_RESULT","FINANCIAL_DATA","RISK","ACTION","ACTION_RESULT","MILESTONE",
        "OPEN_QUESTION","EXCLUSION_RULE","PIVOT_REASON","LESSON"
    }
    assert {x.value for x in SourceType} == {
        "USER_EXPLICIT_INPUT","USER_CORRECTION","CUSTOMER_FEEDBACK","EXPERIMENT_RESULT",
        "REAL_PAYMENT","PROJECT_DECISION","AGENT_INFERENCE","DOCUMENT_CLAIM","WEB_SOURCE",
        "SYSTEM_DERIVED","TOOL_RESULT"
    }


def test_project_specific_requires_request_project_id():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    env = cand(scope=MemoryScope.PROJECT_SPECIFIC, key="p.payment")
    ev = write(m, env, project_id=None)
    assert ev.results[0].operation == MemoryOperation.REJECT


def test_write_new_memory():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    ev = write(m, cand(value={"hours_per_week": 8}))
    assert ev.results[0].operation == MemoryOperation.WRITE
    assert len(repo.memories) == 1


def test_exact_duplicate_merges_without_confidence_inflation():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    first = write(m, cand(cid="C1", value={"hours_per_week":8}), idem="I1")
    mid = first.results[0].new_memory_record.memory_id
    second = write(m, cand(cid="C2", value={"hours_per_week":8}), idem="I2")
    assert second.results[0].operation == MemoryOperation.MERGE
    assert second.results[0].target_memory_id == mid
    assert len(repo.memories) == 1


def test_user_correction_supersedes_and_preserves_history():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    first = write(m, cand(cid="C1", value={"hours_per_week":20}, valid_from=NOW-timedelta(days=30)), idem="I1")
    old_id = first.results[0].new_memory_record.memory_id
    env2 = cand(cid="C2", content="Founder can now allocate 5 hours/week.", value={"hours_per_week":5}, source=SourceType.USER_CORRECTION, valid_from=NOW, key="founder.available_time")
    second = write(m, env2, idem="I2")
    assert second.results[0].operation == MemoryOperation.SUPERSEDE
    assert repo.get(old_id).record.status == MemoryStatus.SUPERSEDED
    assert second.results[0].new_memory_record.supersedes_memory_id == old_id


def test_same_semantic_key_incompatible_current_values_create_conflict():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    write(m, cand(cid="C1", content="Available cash is CNY 80,000.", value={"amount":80000,"currency":"CNY"}, source=SourceType.TOOL_RESULT, key="founder.available_cash"), idem="I1")
    env2 = cand(cid="C2", content="Available cash should be CNY 150,000.", value={"amount":150000,"currency":"CNY"}, source=SourceType.USER_EXPLICIT_INPUT, key="founder.available_cash")
    ev = write(m, env2, idem="I2")
    assert ev.results[0].operation == MemoryOperation.CONFLICT
    assert len(repo.conflicts) == 1
    assert all(x.record.status == MemoryStatus.CONFLICTED for x in repo.memories.values())


def test_agent_inference_cannot_create_verified_fact_without_evidence():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    env = cand(cid="C1", typ=MemoryType.FOUNDER_FACT, content="Founder is highly risk-averse.", source=SourceType.AGENT_INFERENCE, fact=FactStatus.VERIFIED, key="founder.risk_profile")
    ev = write(m, env)
    assert ev.results[0].operation == MemoryOperation.REJECT


def test_wrong_store_financial_snapshot_rejected_from_memory():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    env = cand(cid="C1", typ=MemoryType.FINANCIAL_DATA, content="Current CAC is CNY 800.", store=ProperStore.FINANCIAL_SNAPSHOT, key="project.cac")
    ev = write(m, env)
    assert ev.results[0].operation == MemoryOperation.REJECT
    assert not repo.memories


def test_project_isolation_in_retrieval():
    repo = InMemoryMemoryRepository()
    for pid, mid in [("P1","M1"),("P2","M2")]:
        r = MemoryRecord(memory_id=mid,user_id="U1",project_id=pid,scope=MemoryScope.PROJECT_SPECIFIC,memory_type=MemoryType.LESSON,content=f"Lesson {pid}",fact_status=FactStatus.VERIFIED,confidence=ConfidenceLevel.HIGH,importance=ImportanceLevel.HIGH,status=MemoryStatus.ACTIVE,created_at=NOW,updated_at=NOW)
        repo.upsert(PersistedMemory(r, semantic_key=f"lesson.{pid}"))
    q = MemoryRetrievalQuery(request_id="R",user_id="U1",project_id="P1",memory_types=[MemoryType.LESSON],max_results=10)
    found = retrieve_memories(repo.list_for_user("U1"), q)
    assert [x.record.memory_id for x in found] == ["M1"]


def test_matchmaking_only_receives_matchable_memory():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    write(m, cand(cid="P", typ=MemoryType.CAPABILITY, content="Private sales capability", access=AccessClass.PRIVATE, key="cap.private"), idem="I1")
    write(m, cand(cid="M", typ=MemoryType.CAPABILITY, content="Matchable enterprise sales capability", access=AccessClass.MATCHABLE, key="cap.match"), idem="I2")
    bundle = ContextBuilder(repo).build(ContextBuildRequest(request_id="CTX",user_id="U1",agent_id=AgentId.A9_FOUNDER_MATCHMAKING,task="find cofounder",max_memory_records=20))
    texts = [r.content for r in bundle.founder_stable_memory]
    assert "Matchable enterprise sales capability" in texts
    assert "Private sales capability" not in texts


def test_context_builder_surfaces_conflict():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    write(m, cand(cid="C1", content="Available cash is 80k.", value={"amount":80000}, source=SourceType.TOOL_RESULT, key="cash"), idem="I1")
    write(m, cand(cid="C2", content="Available cash is 150k.", value={"amount":150000}, source=SourceType.USER_EXPLICIT_INPUT, key="cash"), idem="I2")
    b = ContextBuilder(repo).build(ContextBuildRequest(request_id="CTX",user_id="U1",agent_id=AgentId.A0_ORCHESTRATOR,task="can I fund this?"))
    assert len(b.conflict_alerts) == 1


def test_idempotency_same_candidate_not_rewritten():
    repo = InMemoryMemoryRepository(); m = MemoryManager(repo)
    env = cand(cid="C1", value={"hours_per_week":8})
    a = write(m, env, idem="SAME")
    b = write(m, env, idem="SAME")
    assert a.results[0].new_memory_record.memory_id == b.results[0].new_memory_record.memory_id
    assert len(repo.memories) == 1
