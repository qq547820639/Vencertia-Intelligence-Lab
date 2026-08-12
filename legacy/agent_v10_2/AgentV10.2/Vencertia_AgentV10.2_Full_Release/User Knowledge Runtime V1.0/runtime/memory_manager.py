from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .memory_conflict_resolver import ConservativeSemanticAdjudicator, SemanticAdjudicator, SemanticRelation
from .memory_deduplicator import exact_duplicate
from .memory_repository import MemoryRepository, PersistedMemory
from .memory_write_policy import (
    requires_founder_profile_refresh,
    requires_project_snapshot_refresh,
    validate_candidate_authority,
)
from .models import (
    ConfidenceLevel,
    MemoryConflict,
    MemoryOperation,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    MemoryWriteEvaluation,
    MemoryWriteRequest,
    MemoryWriteResult,
    RuntimeRefreshSignals,
    SourceType,
)


def _now():
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _record_from_candidate(request: MemoryWriteRequest, envelope, status=MemoryStatus.ACTIVE, supersedes=None, conflicts=None):
    c = envelope.candidate
    now = _now()
    return MemoryRecord(
        memory_id=_new_id("M"),
        user_id=request.user_id,
        project_id=request.project_id if c.proposed_scope == MemoryScope.PROJECT_SPECIFIC else None,
        scope=c.proposed_scope,
        memory_type=c.proposed_memory_type,
        content=c.content,
        structured_value=c.structured_value,
        source_message_ids=list(dict.fromkeys(c.source_message_ids)),
        source_entity_ids=list(dict.fromkeys(c.source_entity_ids)),
        evidence_ids=list(dict.fromkeys(envelope.evidence_ids)),
        fact_status=c.fact_status,
        confidence=c.confidence,
        importance=c.importance,
        status=status,
        created_at=now,
        updated_at=now,
        valid_from=c.valid_from,
        valid_to=c.valid_to,
        supersedes_memory_id=supersedes,
        conflicts_with_memory_ids=conflicts or [],
    )


class MemoryManager:
    def __init__(self, repository: MemoryRepository, adjudicator: SemanticAdjudicator | None = None):
        self.repository = repository
        self.adjudicator = adjudicator or ConservativeSemanticAdjudicator()

    def write(self, request: MemoryWriteRequest) -> MemoryWriteEvaluation:
        results = []
        conflicts_created = []
        supersessions_created = []
        rejected = []
        founder_refresh = False
        project_refresh = False
        routing_reassess = False
        state_reassess = False

        for envelope in request.candidates:
            c = envelope.candidate
            cached = self.repository.load_idempotent_result(
                request.user_id, request.idempotency_key, c.candidate_id
            )
            if cached is not None:
                results.append(cached)
                continue

            result, conflict_id = self._write_one(request, envelope)
            self.repository.save_idempotent_result(
                request.user_id, request.idempotency_key, c.candidate_id, result
            )
            results.append(result)
            if result.operation == MemoryOperation.REJECT:
                rejected.append(c.candidate_id)
            if result.operation == MemoryOperation.SUPERSEDE and result.target_memory_id:
                supersessions_created.append(result.target_memory_id)
            if conflict_id:
                conflicts_created.append(conflict_id)

            if result.operation != MemoryOperation.REJECT:
                founder_refresh |= requires_founder_profile_refresh(envelope)
                project_refresh |= requires_project_snapshot_refresh(envelope)
                if str(c.importance) == "CRITICAL" or str(c.proposed_memory_type) in {"CONSTRAINT", "RED_LINE", "PROJECT_DECISION", "RISK"}:
                    routing_reassess = True
                    state_reassess = str(c.proposed_memory_type) in {"PROJECT_DECISION", "RISK", "CONSTRAINT", "RED_LINE"}

        snapshot_refresh = any(r.snapshot_refresh_required for r in results)
        context_refresh = any(r.context_index_refresh_required for r in results)
        return MemoryWriteEvaluation(
            request_id=request.request_id,
            user_id=request.user_id,
            project_id=request.project_id,
            candidate_count=len(request.candidates),
            results=results,
            conflicts_created=conflicts_created,
            supersessions_created=supersessions_created,
            rejected_candidates=rejected,
            snapshot_refresh_required=snapshot_refresh,
            context_refresh_required=context_refresh,
            write_confidence=ConfidenceLevel.HIGH,
            runtime_refresh_signals=RuntimeRefreshSignals(
                founder_profile_refresh_required=founder_refresh,
                project_snapshot_refresh_required=project_refresh,
                context_refresh_required=context_refresh,
                routing_reassessment_recommended=routing_reassess,
                state_reassessment_recommended=state_reassess,
            ),
        )

    def _reject(self, request, envelope, reason: str):
        c = envelope.candidate
        return MemoryWriteResult(
            candidate_id=c.candidate_id,
            operation=MemoryOperation.REJECT,
            scope=c.proposed_scope,
            project_id=request.project_id if c.proposed_scope == MemoryScope.PROJECT_SPECIFIC else None,
            memory_type=c.proposed_memory_type,
            reason=reason,
            fact_status=c.fact_status,
            confidence=c.confidence,
            importance=c.importance,
            snapshot_refresh_required=False,
            context_index_refresh_required=False,
        )

    def _write_one(self, request, envelope):
        c = envelope.candidate
        if c.proposed_scope == MemoryScope.PROJECT_SPECIFIC and not request.project_id:
            return self._reject(request, envelope, "PROJECT_SPECIFIC candidate requires project_id."), None

        authority_error = validate_candidate_authority(envelope)
        if authority_error:
            return self._reject(request, envelope, authority_error), None

        project_id = request.project_id if c.proposed_scope == MemoryScope.PROJECT_SPECIFIC else None
        family = self.repository.find_semantic_family(
            request.user_id, project_id, envelope.semantic_key, c.proposed_memory_type, c.content
        )

        if not family:
            record = _record_from_candidate(request, envelope)
            self.repository.upsert(PersistedMemory(record, envelope.semantic_key, set(envelope.source_types), envelope.access_class))
            return MemoryWriteResult(
                candidate_id=c.candidate_id,
                operation=MemoryOperation.WRITE,
                scope=c.proposed_scope,
                project_id=record.project_id,
                memory_type=c.proposed_memory_type,
                new_memory_record=record,
                affected_memory_ids=[record.memory_id],
                reason="New durable Memory; no equivalent active Memory found.",
                fact_status=c.fact_status,
                confidence=c.confidence,
                importance=c.importance,
                snapshot_refresh_required=requires_project_snapshot_refresh(envelope),
                context_index_refresh_required=True,
            ), None

        existing_item = family[0]
        existing = existing_item.record
        relation = self.adjudicator.adjudicate(envelope, existing)

        if relation in {SemanticRelation.EQUIVALENT, SemanticRelation.DETAIL_EXTENSION}:
            now = _now()
            merged = existing.model_copy(deep=True)
            merged.updated_at = now
            merged.source_message_ids = list(dict.fromkeys(existing.source_message_ids + c.source_message_ids))
            merged.source_entity_ids = list(dict.fromkeys(existing.source_entity_ids + c.source_entity_ids))
            merged.evidence_ids = list(dict.fromkeys(existing.evidence_ids + envelope.evidence_ids))
            if relation == SemanticRelation.DETAIL_EXTENSION:
                merged.content = c.content
                merged.structured_value = c.structured_value or existing.structured_value
            # Repetition alone must not inflate confidence. Upgrade only with genuinely new evidence.
            if set(envelope.evidence_ids) - set(existing.evidence_ids):
                merged.confidence = c.confidence
            if str(c.importance) == "CRITICAL":
                merged.importance = c.importance
            self.repository.upsert(PersistedMemory(merged, existing_item.semantic_key or envelope.semantic_key, existing_item.source_types | set(envelope.source_types), existing_item.access_class))
            return MemoryWriteResult(
                candidate_id=c.candidate_id,
                operation=MemoryOperation.MERGE,
                scope=c.proposed_scope,
                project_id=merged.project_id,
                memory_type=c.proposed_memory_type,
                target_memory_id=merged.memory_id,
                new_memory_record=merged,
                affected_memory_ids=[merged.memory_id],
                reason="Equivalent/detailed durable Memory merged without destructive history loss.",
                fact_status=merged.fact_status,
                confidence=merged.confidence,
                importance=merged.importance,
                snapshot_refresh_required=requires_project_snapshot_refresh(envelope),
                context_index_refresh_required=True,
            ), None

        if relation == SemanticRelation.UNSURE:
            return self._reject(request, envelope, "Weaker/uncertain inference cannot replace current verified durable Memory."), None

        if relation == SemanticRelation.TEMPORAL_UPDATE:
            now = _now()
            # Supersede all active/conflicted records in this semantic family to avoid dual current truth.
            affected = []
            for item in family:
                old = item.record.model_copy(deep=True)
                old.status = MemoryStatus.SUPERSEDED
                old.updated_at = now
                if old.valid_to is None and c.valid_from:
                    old.valid_to = c.valid_from
                self.repository.upsert(PersistedMemory(old, item.semantic_key, item.source_types, item.access_class))
                affected.append(old.memory_id)
            new_record = _record_from_candidate(request, envelope, status=MemoryStatus.ACTIVE, supersedes=existing.memory_id)
            self.repository.upsert(PersistedMemory(new_record, envelope.semantic_key, set(envelope.source_types), envelope.access_class))
            affected.append(new_record.memory_id)
            return MemoryWriteResult(
                candidate_id=c.candidate_id,
                operation=MemoryOperation.SUPERSEDE,
                scope=c.proposed_scope,
                project_id=new_record.project_id,
                memory_type=c.proposed_memory_type,
                target_memory_id=existing.memory_id,
                new_memory_record=new_record,
                affected_memory_ids=affected,
                reason="New value is an explicit correction or later-valid value; old history preserved as SUPERSEDED.",
                fact_status=c.fact_status,
                confidence=c.confidence,
                importance=c.importance,
                snapshot_refresh_required=requires_project_snapshot_refresh(envelope),
                context_index_refresh_required=True,
            ), None

        if relation == SemanticRelation.CONFLICT:
            new_record = _record_from_candidate(request, envelope, status=MemoryStatus.CONFLICTED, conflicts=[existing.memory_id])
            old = existing.model_copy(deep=True)
            old.status = MemoryStatus.CONFLICTED
            old.updated_at = _now()
            old.conflicts_with_memory_ids = list(dict.fromkeys(old.conflicts_with_memory_ids + [new_record.memory_id]))
            self.repository.upsert(PersistedMemory(old, existing_item.semantic_key, existing_item.source_types, existing_item.access_class))
            self.repository.upsert(PersistedMemory(new_record, envelope.semantic_key, set(envelope.source_types), envelope.access_class))
            conflict = MemoryConflict(
                conflict_id=_new_id("MC"),
                user_id=request.user_id,
                project_id=project_id,
                semantic_key=envelope.semantic_key,
                memory_ids=[old.memory_id, new_record.memory_id],
                reason="Two current claims for the same semantic key are incompatible; Context Builder must surface the conflict explicitly.",
                created_at=_now(),
            )
            self.repository.add_conflict(conflict)
            return MemoryWriteResult(
                candidate_id=c.candidate_id,
                operation=MemoryOperation.CONFLICT,
                scope=c.proposed_scope,
                project_id=new_record.project_id,
                memory_type=c.proposed_memory_type,
                target_memory_id=old.memory_id,
                new_memory_record=new_record,
                affected_memory_ids=[old.memory_id, new_record.memory_id],
                reason=conflict.reason,
                fact_status=c.fact_status,
                confidence=c.confidence,
                importance=c.importance,
                snapshot_refresh_required=requires_project_snapshot_refresh(envelope),
                context_index_refresh_required=True,
            ), conflict.conflict_id

        # DISTINCT under the same content family is possible only with custom adjudicator; safely WRITE.
        record = _record_from_candidate(request, envelope)
        self.repository.upsert(PersistedMemory(record, envelope.semantic_key, set(envelope.source_types), envelope.access_class))
        return MemoryWriteResult(
            candidate_id=c.candidate_id,
            operation=MemoryOperation.WRITE,
            scope=c.proposed_scope,
            project_id=record.project_id,
            memory_type=c.proposed_memory_type,
            new_memory_record=record,
            affected_memory_ids=[record.memory_id],
            reason="Semantically distinct durable Memory.",
            fact_status=c.fact_status,
            confidence=c.confidence,
            importance=c.importance,
            snapshot_refresh_required=requires_project_snapshot_refresh(envelope),
            context_index_refresh_required=True,
        ), None
