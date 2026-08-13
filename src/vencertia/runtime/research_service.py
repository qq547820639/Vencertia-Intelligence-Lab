"""ResearchExecutionService — the SINGLE shared research pipeline (P0-5/P2-16).

Three callers share this one implementation:
  1. SolveOrchestrator.solve main loop  (via ``run_solve_round``)
  2. POST /v1/research/run              (via ``run_plan``)
  3. CLI ``research run``               (via ``run_plan``)

Before v1.1.2 the API/CLI paths only stored the research trace and silently
discarded candidate evidence — they never ran claim binding, belief updates,
conflict detection or the stop rule. That divergence is the P0-5 defect.

Design notes:
- ``_execute_round`` implements search/retrieval (external IO) → candidate
  evidence → ResearchTrace. It is the only place SearchProvider/RetrievalProvider
  are invoked for research.
- ``run_plan`` runs the FULL pipeline per round: search → dedup → claim binding
  (project_id backfill, P0-3) → conflict → belief update → stop rule → persist.
- ``run_solve_round`` returns ``(trace, candidates)`` so the solve loop keeps
  its exact v1.1.1 processing order (behavior-compatible); both paths use the
  same ``_execute_round`` search implementation and the same engines.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import Field

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    ClaimBindingInput,
    Decision,
    Direction,
    Evidence,
    EvidenceConflict,
    Project,
    ResearchPlan,
    ResearchStopReport,
    ResearchTrace,
    Scope,
    VencertiaBaseModel,
    utcnow,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.providers.models import ModelProvider, RetrievalProvider, SearchProvider
from vencertia.repositories.base import Repository
from vencertia.runtime.belief_engine import BeliefUpdateInput
from vencertia.runtime.evidence_policy import EvidencePolicy


class ResearchExecutionResult(VencertiaBaseModel):
    """Complete output of a research plan execution (additive, P0-5)."""

    plan_id: str
    decision_id: str
    traces: list[ResearchTrace] = Field(default_factory=list)
    candidate_evidence: list[Evidence] = Field(default_factory=list)
    applied_evidence: list[Evidence] = Field(default_factory=list)
    rejected_evidence: list[dict] = Field(default_factory=list)
    bindings: list = Field(default_factory=list)
    belief_updates: list[Belief] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    stop_report: ResearchStopReport | None = None


def evidence_to_result(evidence: Evidence) -> dict:
    """Serialize an Evidence record into a research-result dict for the
    ClaimBindingEngine (single shared implementation)."""
    return {
        "evidence_id": evidence.id,
        "id": evidence.id,
        "scope": evidence.scope.value if hasattr(evidence.scope, "value") else evidence.scope,
        "evidence_type": (
            evidence.evidence_type.value
            if hasattr(evidence.evidence_type, "value")
            else evidence.evidence_type
        ),
        "source": evidence.source,
        "url": (evidence.provenance.source_url or "") if evidence.provenance else "",
        "supports_or_contradicts": (
            evidence.supports_or_contradicts.value
            if hasattr(evidence.supports_or_contradicts, "value")
            else evidence.supports_or_contradicts
        ),
        "directness": evidence.directness,
        "reliability": evidence.reliability,
        "relevance": evidence.relevance,
        "strength": evidence.strength,
        "independence_group": evidence.independence_group,
        "authority_level": (
            evidence.authority_level.value
            if hasattr(evidence.authority_level, "value")
            else evidence.authority_level
        ),
        "verification": (
            evidence.verification.value
            if hasattr(evidence.verification, "value")
            else evidence.verification
        ),
        "content_fingerprint": evidence.content_fingerprint,
        "canonical_source_id": evidence.canonical_source_id,
        "source_family": evidence.source_family,
        "project_id": evidence.project_id,
    }


class ResearchExecutionService:
    """Runs research plans and single solve rounds against one pipeline."""

    def __init__(
        self,
        repo: Repository,
        engines,
        policy: EvidencePolicy,
        settings: Settings | None = None,
        bus: EventBus | None = None,
        model: ModelProvider | None = None,
        search: SearchProvider | None = None,
        retrieval: RetrievalProvider | None = None,
    ) -> None:
        self.repo = repo
        self.engines = engines
        self.policy = policy
        self.settings = settings or get_settings()
        self.bus = bus or EventBus()
        self.model = model
        self.search = search
        self.retrieval = retrieval

    # -- public API -----------------------------------------------------------

    def run_plan(
        self,
        decision_id: str,
        question_ids: list[str] | None = None,
        max_queries: int | None = None,
    ) -> ResearchExecutionResult:
        """Execute a research plan end-to-end (API/CLI path).

        Loads the decision + project, reuses the latest persisted plan or
        creates one, then runs the full round pipeline for each selected
        question. Applied evidence / bindings / belief updates / conflicts /
        traces are persisted; the returned :class:`ResearchExecutionResult`
        carries the complete outcome.
        """
        decision = self.repo.get_decision(decision_id)
        if decision is None:
            from vencertia.repositories.base import EntityNotFoundError

            raise EntityNotFoundError("decision", decision_id)
        project = self.repo.get_project(decision.project_id)
        plan = self._load_or_create_plan(decision, project)
        context = self._build_context(decision, project)

        traces: list[ResearchTrace] = []
        all_applied: list[Evidence] = []
        all_candidates: list[Evidence] = []
        rejected_evidence: list[dict] = []
        bindings: list = []
        all_conflicts: list[EvidenceConflict] = []
        belief_updates: list[Belief] = []
        stop_report: ResearchStopReport | None = None

        questions = self._select_questions(plan, question_ids, max_queries)
        for round_no, question in enumerate(questions, start=1):
            # External IO (search/retrieval) happens OUTSIDE the transaction.
            trace, candidates = self._execute_round(
                decision=decision,
                project=project,
                question_id=question.id,
                queries=question.search_queries or [question.question],
                problem_text=decision.decision_question,
            )
            all_candidates.extend(candidates)

            # P2-17: the deterministic mutation batch (dedup → binding →
            # conflict → belief updates → trace save) is ATOMIC. A failure in
            # the middle rolls the whole round back — no half batch.
            state: dict = {}
            # Bind loop variables as default args: the closure runs
            # synchronously inside in_transaction (ruff B023).
            def _round_batch(
                _state=state,
                _trace=trace,
                _candidates=candidates,
                _round_no=round_no,
            ) -> None:  # noqa: B023
                kept = self._dedup_candidates(_candidates, _trace)
                applied, rejected, round_bindings = self._bind_candidates(
                    kept, context, decision, project
                )
                _trace.new_evidence_ids = [e.id for e in applied]
                _state["rejected"] = rejected
                _state["round_bindings"] = round_bindings
                _state["applied"] = applied

                conflicts = self._detect_conflicts(list(all_applied) + applied)
                _state["conflicts"] = conflicts
                for conflict in conflicts:
                    self.repo.save_evidence_conflict(conflict)

                beliefs_before = self.repo.get_beliefs(
                    project.id if project else decision.project_id
                )
                _state["beliefs_before"] = beliefs_before
                if applied:
                    _state["updated"] = self._update_beliefs(applied, conflicts, _trace.id)

                beliefs_now = self.repo.get_beliefs(
                    project.id if project else decision.project_id
                )
                target_claims = [b.claim_id for b in beliefs_now]
                latency_ms = 0.0
                if _trace.completed_at is not None and _trace.started_at is not None:
                    latency_ms = (
                        _trace.completed_at - _trace.started_at
                    ).total_seconds() * 1000.0
                from vencertia.runtime.research_stop import RoundSummary

                # M0-2: real decision_sensitivity_signal — feed the
                # recommendation before/after this round's belief update.
                decision_result_before = None
                decision_result_after = None
                if decision is not None and len(decision.options) >= 2:
                    from vencertia.runtime.decision_engine import DecisionEngineInput

                    try:
                        decision_result_before = self.engines.decision_engine.evaluate(
                            DecisionEngineInput(
                                decision=decision,
                                beliefs=beliefs_before,
                                risk_aversion=self.settings.risk_aversion,
                                minimum_margin=self.settings.minimum_margin,
                                max_critical_uncertainty=self.settings.max_critical_uncertainty,
                            )
                        )
                        decision_result_after = self.engines.decision_engine.evaluate(
                            DecisionEngineInput(
                                decision=decision,
                                beliefs=beliefs_now,
                                risk_aversion=self.settings.risk_aversion,
                                minimum_margin=self.settings.minimum_margin,
                                max_critical_uncertainty=self.settings.max_critical_uncertainty,
                            )
                        )
                    except Exception:  # pragma: no cover - stop signal must not block research
                        decision_result_before = None
                        decision_result_after = None

                _state["stop_report"] = self._evaluate_stop(
                    traces,
                    beliefs_before,
                    beliefs_now,
                    target_claims,
                    decision,
                    _round_no,
                    round_summary=RoundSummary(
                        applied_evidence=applied,
                        bindings=list(bindings) + round_bindings,
                        target_claim_ids=target_claims,
                        beliefs_before=beliefs_before,
                        beliefs_after=beliefs_now,
                        decision_result_before=decision_result_before,
                        decision_result_after=decision_result_after,
                        queries_executed=_trace.queries_executed,
                        latency_ms=latency_ms,
                    ),
                )
                _trace.stop_status = _state["stop_report"].status
                _trace.stop_reason = _state["stop_report"].reason
                self.repo.save_research_trace(_trace)

            self.repo.in_transaction(_round_batch)

            applied = state.get("applied", [])
            rejected = state.get("rejected", [])
            round_bindings = state.get("round_bindings", [])
            conflicts = state.get("conflicts", [])
            stop_report = state.get("stop_report")
            rejected_evidence.extend(rejected)
            bindings.extend(round_bindings)
            all_applied.extend(applied)
            all_conflicts.extend(conflicts)
            if state.get("updated"):
                belief_updates.extend(state["updated"])
            traces.append(trace)

            if stop_report is not None and stop_report.status != "RESEARCH_MORE":
                break

        return ResearchExecutionResult(
            plan_id=plan.id,
            decision_id=decision.id,
            traces=traces,
            candidate_evidence=all_candidates,
            applied_evidence=all_applied,
            rejected_evidence=rejected_evidence,
            bindings=bindings,
            belief_updates=belief_updates,
            conflicts=all_conflicts,
            stop_report=stop_report,
        )

    def run_solve_round(
        self,
        request: Any,
        project: Project,
        decision: Decision,
        plan: ResearchPlan,
        round_no: int,
    ) -> tuple[ResearchTrace, list[Evidence]]:
        """Execute ONE search round for the solve main loop (P0-5).

        Behavior-identical to the v1.1.1 ``SolveOrchestrator._run_research_round``:
        search/retrieval → candidate evidence → trace. The solve loop continues
        to own dedup/binding/belief-update/stop so its SolveResult stays
        byte-for-byte compatible. The search implementation itself is the same
        ``_execute_round`` used by ``run_plan``.
        """
        question = plan.questions[(round_no - 1) % len(plan.questions)]
        queries = question.search_queries or [question.question]
        return self._execute_round(
            decision=decision,
            project=project,
            question_id=question.id,
            queries=queries,
            problem_text=request.problem_text,
        )

    # -- internals -------------------------------------------------------------

    def _load_or_create_plan(
        self, decision: Decision, project: Project | None
    ) -> ResearchPlan:
        plans = self.repo.list_research_plans(decision.id)
        if plans:
            return plans[-1]
        planner = self.engines.research_planner
        if planner is None:
            from vencertia.runtime.research_planner import ResearchPlanner

            planner = ResearchPlanner(settings=self.settings, repo=self.repo)
        beliefs = self.repo.get_beliefs(decision.project_id)
        context = self._build_context(decision, project)
        criticals = self.engines.uncertainty_engine.rank(decision, beliefs)
        plan = planner.plan(decision, beliefs, criticals, context)
        self.repo.save_research_plan(plan)
        self._emit(
            EventType.RESEARCH_PLANNED,
            "research_plan",
            plan.id,
            {"question_count": len(plan.questions)},
        )
        return plan

    def _build_context(self, decision: Decision, project: Project | None):
        builder = self.engines.context_builder_v11
        if builder is not None:
            user_id = project.user_id if project is not None else None
            return builder.build_for_decision(
                decision.project_id, user_id=user_id, limit=15, decision=decision
            )
        return self.engines.context_builder.build(decision.project_id, limit=15)

    @staticmethod
    def _select_questions(
        plan: ResearchPlan,
        question_ids: list[str] | None,
        max_queries: int | None,
    ) -> list:
        questions = plan.questions
        if question_ids:
            wanted = set(question_ids)
            questions = [q for q in questions if q.id in wanted]
        if max_queries is not None and max_queries > 0:
            questions = questions[:max_queries]
        return questions

    def _execute_round(
        self,
        decision: Decision,
        project: Project | None,
        question_id: str,
        queries: list[str],
        problem_text: str,
    ) -> tuple[ResearchTrace, list[Evidence]]:
        """Search/retrieval → candidate evidence → trace (external IO only)."""
        start = utcnow()
        candidates: list[Evidence] = []
        queries_executed = 0
        results_retrieved = 0
        trace_notes: list[str] = []
        project_id = project.id if project is not None else None

        if self.search is not None:
            from vencertia.providers.errors import ProviderError
            from vencertia.providers.search import SearchAdapter

            adapter = SearchAdapter(self.search)
            for query in queries[: self.settings.research_queries_per_round]:
                queries_executed += 1
                try:
                    evidence_list = adapter.to_candidate_evidence(
                        query, claim_ids=[], direction=Direction.SUPPORTS.value, k=2
                    )
                except ProviderError as exc:
                    # GAP-02: a failed search provider must NOT fabricate
                    # evidence and must NOT silently fall back to mock. Record
                    # the failure; the stop rule will declare SEARCH_EXHAUSTED.
                    provider_name = getattr(self.search, "name", "search")
                    self._emit(
                        EventType.PROVIDER_FAILED,
                        "search_provider",
                        provider_name,
                        {"query": query, "error_type": exc.error_type, "message": str(exc)},
                    )
                    trace_notes.append(
                        f"search provider failed ({provider_name}): {exc.error_type}"
                    )
                    continue
                for ev in evidence_list:
                    if project_id is not None and ev.project_id is None:
                        ev.project_id = project_id  # P0-3: "为该项目收集的"
                    candidates.append(ev)
                results_retrieved += len(evidence_list)

        if self.retrieval is not None:
            docs = self.retrieval.retrieve(problem_text, k=3)
            for doc in docs:
                candidates.append(self._doc_to_evidence(doc, project_id))
                results_retrieved += 1

        provider = getattr(self.search, "name", "search") if self.search else "retrieval"
        model = getattr(self.model, "name", "mock") if self.model else "mock"
        trace = ResearchTrace(
            id="RT_" + uuid4().hex,
            decision_id=decision.id,
            question_id=question_id,
            started_at=start,
            completed_at=utcnow(),
            query="; ".join(queries[: self.settings.research_queries_per_round]),
            queries_executed=queries_executed,
            results_retrieved=results_retrieved,
            provider=provider,
            model=model,
            request_id="req_" + uuid4().hex,
            notes=trace_notes,
        )
        return trace, candidates

    @staticmethod
    def _doc_to_evidence(doc, project_id: str | None = None) -> Evidence:
        content = str(doc.content or "")
        lowered = content.lower()
        direction = Direction.SUPPORTS.value
        if "0 of" in lowered or "0/4" in lowered or "no " in lowered and "paid" in lowered:
            direction = Direction.CONTRADICTS.value
        source_text = content
        from vencertia.providers.search import (
            canonical_source,
            content_fingerprint,
            source_family,
        )

        return Evidence(
            id=f"E_{uuid4().hex}",
            claim_ids=[],
            scope=Scope.MARKET,
            evidence_type="REVIEWED_EXTERNAL_RESEARCH",
            provenance={"tool": "RetrievalProvider", "source_id": doc.id, "raw_extract": content},
            source=source_text,
            directness=0.5,
            reliability=0.6,
            relevance=0.6,
            strength=0.5,
            supports_or_contradicts=direction,
            independence_group=f"retrieval:{doc.id}",
            observed_at=utcnow(),
            authority_level="REVIEWED_EXTERNAL_RESEARCH",
            verification="ESTIMATED",
            content_fingerprint=content_fingerprint(source_text),
            canonical_source_id=canonical_source("", str(doc.metadata.get("source", "retrieval"))),
            source_family=source_family("", str(doc.metadata.get("source", "retrieval"))),
            project_id=project_id,
        )

    def _dedup_candidates(
        self, candidates: list[Evidence], trace: ResearchTrace
    ) -> list[Evidence]:
        kept = candidates
        if self.engines.dedup_engine is not None:
            dedup = self.engines.dedup_engine.group(candidates)
            trace.duplicate_dropped = len(dedup.dropped_ids)
            kept_ids = set(dedup.kept_ids)
            kept = [c for c in candidates if c.id in kept_ids]
        # Drop candidates whose content was already applied in an earlier round
        # (same fingerprint) — do not re-apply twice.
        existing_fingerprints = {
            e.content_fingerprint
            for e in self.repo.list_evidence()
            if e.content_fingerprint
        }
        kept = [
            c
            for c in kept
            if not c.content_fingerprint or c.content_fingerprint not in existing_fingerprints
        ]
        return kept

    def _bind_candidates(
        self,
        kept: list[Evidence],
        context,
        decision: Decision,
        project: Project | None,
    ) -> tuple[list[Evidence], list[dict], list]:
        if self.engines.claim_binding_engine is None or not kept:
            return [], [], []
        project_id = project.id if project is not None else None
        binding_output = self.engines.claim_binding_engine.process(
            ClaimBindingInput(
                research_results=[evidence_to_result(e) for e in kept],
                context=context,
                existing_claims=self.repo.list_claims(decision.project_id),
                auto_extract=True,
                binding_confidence_threshold=self.settings.binding_confidence_threshold,
            )
        )
        applied = [Evidence.model_validate(e) for e in binding_output.applied_evidence]
        # P0-3: ensure applied evidence is owned by the collecting project.
        for ev in applied:
            if ev.project_id is None and project_id is not None:
                ev.project_id = project_id
        rejected = binding_output.rejected_evidence
        bindings = list(binding_output.bindings) + list(binding_output.unbound)
        return applied, rejected, bindings

    def _detect_conflicts(self, all_applied: list[Evidence]) -> list[EvidenceConflict]:
        if not all_applied or self.engines.conflict_engine is None:
            return []
        evidence_by_claim: dict[str, list[Evidence]] = {}
        for evidence in all_applied:
            for cid in evidence.claim_ids:
                evidence_by_claim.setdefault(cid, []).append(evidence)
        return self.engines.conflict_engine.detect(evidence_by_claim)

    def _update_beliefs(
        self,
        applied: list[Evidence],
        conflicts: list[EvidenceConflict],
        batch_id: str,
    ) -> list[Belief]:
        if self.engines.belief_engine is None:
            return []
        project_id = self._project_of_evidence(applied[0])
        beliefs_for_update = self.repo.get_beliefs(project_id)
        updated_output = self.engines.belief_engine.update(
            BeliefUpdateInput(
                beliefs=beliefs_for_update,
                evidence=applied,
                policy=self.policy,
                max_pseudo_observations=self.settings.max_pseudo_observations,
                conflict_weight_threshold=self.settings.conflict_weight_threshold,
            )
        )
        raise_by_claim: dict[str, float] = {}
        for conflict in conflicts:
            raise_by_claim[conflict.claim_id] = round(min(1.0, 0.15 * conflict.severity), 6)
        for belief in updated_output.beliefs:
            if belief.claim_id in raise_by_claim:
                new_uncertainty = round(
                    min(1.0, belief.uncertainty + raise_by_claim[belief.claim_id]), 6
                )
                object.__setattr__(belief, "uncertainty", new_uncertainty)
                object.__setattr__(
                    belief, "confidence", max(0.0, min(1.0, 1.0 - new_uncertainty))
                )
        self._save_beliefs(updated_output.beliefs, batch_id=batch_id)
        self._save_belief_update_records(updated_output, conflicts)
        return list(updated_output.beliefs)

    def _project_of_evidence(self, evidence: Evidence) -> str:
        if evidence.project_id:
            return evidence.project_id
        bindings = self.repo.list_bindings(evidence_id=evidence.id)
        if bindings and bindings[0].claim_id:
            claims = self.repo.list_claims()
            for claim in claims:
                if claim.id == bindings[0].claim_id:
                    return claim.project_id or ""
        return ""

    def _evaluate_stop(
        self,
        traces: list[ResearchTrace],
        beliefs_before: list[Belief],
        beliefs_after: list[Belief],
        target_claims: list[str],
        decision: Decision,
        round_no: int,
        round_summary=None,
    ) -> ResearchStopReport:
        if self.engines.research_stop_rule is None:
            from vencertia.domain import ResearchStopReport as _R

            return _R(
                status="RESEARCH_MORE",
                reason="stop rule not wired",
                signals={},
            )
        return self.engines.research_stop_rule.evaluate(
            traces,
            beliefs_before,
            beliefs_after,
            target_claims,
            decision=decision,
            round_no=round_no,
            round_summary=round_summary,
        )

    def _save_beliefs(self, beliefs: list[Belief], batch_id: str | None = None) -> None:
        for belief in beliefs:
            existing = self.repo.get_belief(belief.id)
            expected = existing.version if existing is not None else None
            if batch_id is not None:
                belief.last_evidence_batch_id = batch_id
                belief.policy_version = self.settings.policy_version
            self.repo.save_belief(belief, expected_version=expected)
            self._emit(
                EventType.BELIEF_UPDATED,
                "belief",
                belief.id,
                {"probability": belief.probability, "uncertainty": belief.uncertainty},
            )

    def _save_belief_update_records(
        self, updated_output, conflicts: list[EvidenceConflict] | None = None
    ) -> None:
        conflicts = conflicts or []
        raise_by_claim: dict[str, float] = {}
        for conflict in conflicts:
            raise_by_claim[conflict.claim_id] = round(min(1.0, 0.15 * conflict.severity), 6)
        for record in updated_output.update_records:
            if record.claim_id in raise_by_claim:
                raise_amount = raise_by_claim[record.claim_id]
                record = record.model_copy(
                    update={
                        "conflict_uncertainty_raise": round(
                            record.conflict_uncertainty_raise + raise_amount, 6
                        ),
                        "new_uncertainty": round(
                            min(1.0, record.new_uncertainty + raise_amount), 6
                        ),
                    }
                )
            self.repo.save_belief_update_record(record)

    def _emit(
        self,
        event_type: EventType,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.bus.publish(make_event(event_type, entity_type, entity_id, payload))
