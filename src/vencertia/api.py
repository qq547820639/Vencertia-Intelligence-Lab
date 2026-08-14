"""Vencertia v1.1 REST API (FastAPI).

Unified response envelope: ``{"code": 0, "data": ..., "message": "ok"}``.
Domain errors: EntityNotFoundError -> 404, StaleWriteError -> 409,
ValueError -> 400.

The app is wired through :class:`~vencertia.container.ApplicationContainer`
(ADR-009); ``create_app`` remains a plain function so tests can inject custom
repositories/runtimes.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel, Field

from vencertia.config import Settings
from vencertia.container import build_container
from vencertia.domain import (
    Action,
    ClaimBindingInput,
    DecisionOption,
    Evidence,
    Experiment,
    OutcomeType,
    VencertiaBaseModel,
)
from vencertia.events.types import EventType, make_event
from vencertia.providers.errors import ProviderError
from vencertia.repositories.base import EntityNotFoundError, Repository, StaleWriteError
from vencertia.runtime import EvidenceImporter, SolveOrchestrator, SolveRequest


class ApiResponse(BaseModel):
    code: int = 0
    data: Any = None
    message: str = "ok"


# -- request models ------------------------------------------------------------


class CompileRequest(VencertiaBaseModel):
    project_id: str
    problem_text: str
    options: list[DecisionOption] | None = None
    user_id: str | None = None


class EvaluateRequest(VencertiaBaseModel):
    decision_id: str


class DecisionActRequest(VencertiaBaseModel):
    """v1.9.1: close the review loop on a ledger row (RECOMMENDED → ACTED → SETTLED)."""

    action_taken: str  # what the owner actually did
    result: str | None = None  # set to settle immediately (→ SETTLED)
    outcome_type: OutcomeType | str = OutcomeType.PARTIAL
    quantitative: dict[str, float] = Field(default_factory=dict)


class IdeaAssessRequest(VencertiaBaseModel):
    """v2.0 入口层: raw idea -> decision structure + assumption register."""

    idea_text: str
    domain: str = "general"
    user_id: str | None = None


class BpRequest(VencertiaBaseModel):
    """v2.0 出口层: persisted decision -> business plan."""

    decision_id: str
    company_name: str | None = None
    tagline: str | None = None
    market_note: str | None = None
    narrative: bool = True  # run V11 narrative skills (validated candidates)


class EvidenceRequest(VencertiaBaseModel):
    evidence: Evidence


class EvidenceImportRequest(VencertiaBaseModel):
    """P1-2: batch evidence import — full ``Evidence`` objects, optional owner."""

    items: list[Evidence]
    project_id: str | None = None


class OutcomeRequest(VencertiaBaseModel):
    action_id: str
    result: str
    quantitative: dict[str, float] = Field(default_factory=dict)
    outcome_type: OutcomeType | str = OutcomeType.PARTIAL
    direction: str | None = None


class ExperimentProposeRequest(VencertiaBaseModel):
    decision_id: str
    candidates: list[Experiment] = Field(default_factory=list)
    max_results: int = 5


class ExperimentResolveRequest(VencertiaBaseModel):
    result: str
    outcome_type: OutcomeType | str = OutcomeType.PARTIAL
    quantitative: dict[str, float] = Field(default_factory=dict)


class PredictionCreateRequest(VencertiaBaseModel):
    decision_id: str


class PredictionResolveRequest(VencertiaBaseModel):
    outcome: bool


class CalibrationQuery(BaseModel):
    scope: str = "ALL"
    key: str = "ALL"


class ResearchPlanRequest(VencertiaBaseModel):
    decision_id: str


class ResearchRunRequest(VencertiaBaseModel):
    decision_id: str
    question_ids: list[str] | None = None
    max_queries: int | None = None


class EvidenceBindRequest(VencertiaBaseModel):
    evidence_id: str
    candidate_claims: list[dict] | None = None
    auto_extract: bool = True


class PredictionCorrectRequest(VencertiaBaseModel):
    new_outcome: bool
    source: str


def _register_exception_handlers(app: FastAPI, fail) -> None:
    """Register unified error → envelope handlers (M0-3).

    All handlers return ``{code, data, message}`` while preserving the HTTP
    status code:
      EntityNotFoundError -> 404
      StaleWriteError     -> 409
      ValueError          -> 400
      ProviderError       -> 502
    """
    from fastapi.responses import JSONResponse

    from vencertia.presentation import localize_error_message

    def _response(status_code: int, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=fail(status_code, localize_error_message(exc)).model_dump(mode="json"),
        )

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(_, exc: EntityNotFoundError):
        return _response(404, exc)

    @app.exception_handler(StaleWriteError)
    async def stale_write_handler(_, exc: StaleWriteError):
        return _response(409, exc)

    @app.exception_handler(ValueError)
    async def value_error_handler(_, exc: ValueError):
        return _response(400, exc)

    @app.exception_handler(ProviderError)
    async def provider_error_handler(_, exc: ProviderError):
        return _response(502, exc)


def create_app(
    settings: Settings,
    repo: Repository,
    runtime: SolveOrchestrator,
) -> FastAPI:
    import vencertia

    app = FastAPI(
        title="Vencertia Decision Runtime",
        version=vencertia.__version__,
    )

    def ok(data: Any = None, message: str = "ok") -> ApiResponse:
        return ApiResponse(code=0, data=data, message=message)

    def fail(code: int, message: str) -> ApiResponse:
        return ApiResponse(code=code, data=None, message=message)

    # -- health ---------------------------------------------------------------

    @app.get("/health", response_model=ApiResponse)
    def health() -> ApiResponse:
        return ok(
            {
                "ok": True,
                # v1.1.2 (P1-12): single source of truth for versions.
                "runtime_version": vencertia.__version__,
                "api_contract_version": vencertia.__api_contract_version__,
                "policy_version": settings.policy_version,
                "model_provider": settings.model_provider,
                # Legacy compatibility keys (derived, never hard-coded):
                "version": vencertia.__version__,  # v1.0 health contract alias
                "api_version": vencertia.__api_contract_version__ + ".0",
            }
        )

    # -- decisions -------------------------------------------------------------

    @app.post("/v1/decisions/compile", response_model=ApiResponse)
    def compile_decision(req: CompileRequest) -> ApiResponse:
        project = repo.get_project(req.project_id)
        if project is None:
            raise EntityNotFoundError("project", req.project_id)
        compiled = runtime.compiler.compile(
            req.problem_text,
            {"project_id": req.project_id, "user_id": req.user_id or project.user_id},
            options=req.options,
        )
        return ok(compiled.model_dump(mode="json"))

    @app.post("/v1/decisions/evaluate", response_model=ApiResponse)
    def evaluate_decision(req: EvaluateRequest) -> ApiResponse:
        result, convergence = runtime.evaluate_decision(req.decision_id)
        return ok(
            {
                "decision": result.model_dump(mode="json"),
                "convergence": convergence.model_dump(mode="json"),
            }
        )

    @app.get("/v1/decisions/{decision_id}", response_model=ApiResponse)
    def get_decision(decision_id: str) -> ApiResponse:
        decision = repo.get_decision(decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", decision_id)
        return ok(decision.model_dump(mode="json"))

    @app.post("/v1/decisions/{decision_id}/act", response_model=ApiResponse)
    def act_on_decision(decision_id: str, req: DecisionActRequest) -> ApiResponse:
        """v1.9.1: close the review loop — RECOMMENDED → ACTED (→ SETTLED).

        Marks the decision-ledger row as acted with what the owner actually
        did. When ``result`` is provided, the action is settled immediately
        through the existing outcome closed loop (outcome evidence → belief
        updates → prediction settlement → calibration → decision re-evaluation
        → DecisionOutcomeRecord backfill).
        """
        from vencertia.domain import Action, utcnow
        from vencertia.presentation import (
            DECISION_RECORD_STATUS_ZH,
        )

        decision = repo.get_decision(decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", decision_id)
        record = repo.get_decision_record(decision_id)
        if record is None:
            raise EntityNotFoundError("decision_record", decision_id)
        if record.status == "SETTLED":
            raise ValueError("该决策已复盘（SETTLED），不能重复标记行动")

        holder: dict = {}

        def _batch() -> None:
            if record.status == "RECOMMENDED":
                action = Action(
                    id="ACT_" + uuid4().hex,
                    project_id=decision.project_id,
                    kind="DECISION",
                    description=req.action_taken,
                    decision_id=decision.id,
                    status="RUNNING",
                )
                repo.save_action(action)
                runtime.bus.publish(
                    make_event(
                        EventType.ACTION_CREATED, "action", action.id, {"kind": action.kind}
                    )
                )
                record.action_taken = action.id
                record.status = "ACTED"
                record.updated_at = utcnow()
                record.version += 1
                repo.save_decision_record(record, expected_version=record.version - 1)
                runtime.bus.publish(
                    make_event(EventType.DECISION_ACTED, "decision_record", record.id, {})
                )
                holder["action_id"] = action.id
            else:  # ACTED — reuse the stored action for settlement
                action = repo.get_action(record.action_taken) if record.action_taken else None
                if action is None:
                    raise ValueError("台账已行动但没有对应 Action 记录，无法复盘")
                holder["action_id"] = action.id
            if req.result is not None:
                holder["settlement"] = runtime.record_outcome(
                    holder["action_id"],
                    req.result,
                    quantitative=req.quantitative,
                    outcome_type=req.outcome_type,
                )

        repo.in_transaction(_batch)
        settlement = holder.get("settlement")
        data: dict = {
            "decision_record_id": record.id,
            "decision_id": decision_id,
            "action_id": holder["action_id"],
            "status": "SETTLED" if settlement is not None else "ACTED",
            "status_zh": DECISION_RECORD_STATUS_ZH.get(
                "SETTLED" if settlement is not None else "ACTED"
            ),
        }
        if settlement is not None:
            data["settlement"] = settlement.model_dump(mode="json")
        return ok(data)

    # -- evidence ----------------------------------------------------------------

    @app.post("/v1/evidence", response_model=ApiResponse)
    def add_evidence(req: EvidenceRequest) -> ApiResponse:
        evidence = req.evidence
        # P0-3: if no project_id is supplied, try to derive it from the first
        # claim's owner; otherwise the write boundary rejects the request.
        if not evidence.project_id:
            for cid in (evidence.claim_ids or []):
                claim = repo.get_claim(cid)
                if claim is not None and claim.project_id:
                    evidence = evidence.model_copy(update={"project_id": claim.project_id})
                    break
        grade = runtime.policy.grade(evidence)
        if grade.scope_gate == "REJECTED":
            raise ValueError(grade.reason)
        graded = runtime.policy.apply_authority(evidence, settings.policy_version)
        repo.add_evidence(graded)
        return ok(graded.model_dump(mode="json"), message=grade.reason)

    @app.post("/v1/evidence/import", response_model=ApiResponse)
    def evidence_import(req: EvidenceImportRequest) -> ApiResponse:
        importer = EvidenceImporter(
            repo=repo, policy=runtime.policy, dedup=runtime.engines.dedup_engine
        )
        report = importer.import_batch(req.items, project_id=req.project_id)
        return ok(report.model_dump(mode="json"))

    # -- outcomes ----------------------------------------------------------------

    @app.post("/v1/outcomes", response_model=ApiResponse)
    def record_outcome(req: OutcomeRequest) -> ApiResponse:
        result = runtime.record_outcome(
            req.action_id,
            req.result,
            quantitative=req.quantitative,
            outcome_type=req.outcome_type,
            direction=req.direction,
        )
        return ok(result.model_dump(mode="json"))

    # -- experiments ---------------------------------------------------------------

    @app.post("/v1/experiments/propose", response_model=ApiResponse)
    def propose_experiment(req: ExperimentProposeRequest) -> ApiResponse:
        from vencertia.runtime.experiment_optimizer import ExperimentProposalInput

        decision = repo.get_decision(req.decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", req.decision_id)
        beliefs = repo.get_beliefs(decision.project_id)
        criticals = runtime.engines.uncertainty_engine.rank(decision, beliefs)
        critical_belief_id = criticals[0].belief_id if criticals else None
        proposal = runtime.engines.experiment_optimizer.propose(
            ExperimentProposalInput(
                decision=decision,
                beliefs=beliefs,
                critical_belief_id=critical_belief_id,
                candidates=req.candidates or repo.list_experiments(decision.project_id),
                max_results=req.max_results,
            )
        )
        return ok(
            {
                "decision_insufficient": proposal.decision_insufficient,
                "reason": proposal.reason,
                "ranked": [r.model_dump(mode="json") for r in proposal.ranked],
                "rejected": proposal.rejected,
            }
        )

    @app.post("/v1/experiments/{experiment_id}/resolve", response_model=ApiResponse)
    def resolve_experiment(experiment_id: str, req: ExperimentResolveRequest) -> ApiResponse:
        experiment = repo.get_experiment(experiment_id)
        if experiment is None:
            raise EntityNotFoundError("experiment", experiment_id)
        action = Action(
            id=f"ACT_{experiment_id}",
            project_id="PRJ_UNKNOWN",
            kind="EXPERIMENT",
            description=experiment.action,
            decision_id=experiment.decision_id,
            experiment_id=experiment.id,
            status="RUNNING",
        )
        if experiment.decision_id is not None:
            decision = repo.get_decision(experiment.decision_id)
            if decision is not None:
                action.project_id = decision.project_id
        repo.save_action(action)
        # v1.9: emit the previously-unused lifecycle events at their real
        # boundaries (audit trail for experiment execution).
        runtime.bus.publish(
            make_event(EventType.ACTION_CREATED, "action", action.id, {"kind": action.kind})
        )
        runtime.bus.publish(
            make_event(
                EventType.EXPERIMENT_STARTED,
                "experiment",
                experiment.id,
                {"action_id": action.id},
            )
        )
        result = runtime.record_outcome(
            action.id,
            req.result,
            quantitative=req.quantitative,
            outcome_type=req.outcome_type,
        )
        experiment.status = "RESOLVED_SUPPORT" if result.outcome.outcome_type == "SUCCESS" else (
            "RESOLVED_REFUTE" if result.outcome.outcome_type == "FAILURE" else "RESOLVED_AMBIGUOUS"
        )
        experiment.outcome_evidence_id = result.outcome_evidence.id
        experiment.resolved_at = result.outcome.observed_at
        experiment.version += 1
        repo.save_experiment(experiment, expected_version=experiment.version - 1)
        runtime.bus.publish(
            make_event(
                EventType.EXPERIMENT_RESOLVED,
                "experiment",
                experiment.id,
                {"status": experiment.status, "outcome_id": result.outcome.id},
            )
        )
        return ok(result.model_dump(mode="json"))

    # -- predictions -----------------------------------------------------------------

    @app.post("/v1/predictions", response_model=ApiResponse)
    def create_predictions(req: PredictionCreateRequest) -> ApiResponse:
        decision = repo.get_decision(req.decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", req.decision_id)
        beliefs = repo.get_beliefs(decision.project_id)
        entries = runtime.engines.prediction_ledger.register(decision, beliefs)
        # M0-4: single persistence point — register() no longer saves.
        for entry in entries:
            repo.save_prediction(entry)
        return ok([e.model_dump(mode="json") for e in entries])

    @app.post("/v1/predictions/{prediction_id}/resolve", response_model=ApiResponse)
    def resolve_prediction(prediction_id: str, req: PredictionResolveRequest) -> ApiResponse:
        entry = runtime.engines.prediction_ledger.resolve(prediction_id, req.outcome)
        return ok(entry.model_dump(mode="json"))

    @app.post("/v1/predictions/{prediction_id}/correct", response_model=ApiResponse)
    def correct_prediction(prediction_id: str, req: PredictionCorrectRequest) -> ApiResponse:
        entry = runtime.engines.prediction_ledger.correct(
            prediction_id, req.new_outcome, req.source
        )
        runtime.bus.publish(
            make_event(
                EventType.PREDICTION_CORRECTED,
                "prediction",
                entry.id,
                {"outcome": entry.outcome, "source": req.source, "version": entry.version},
            )
        )
        return ok(entry.model_dump(mode="json"))

    # -- calibration -------------------------------------------------------------------

    @app.get("/v1/calibration", response_model=ApiResponse)
    def calibration_report(scope: str = "ALL", key: str = "ALL") -> ApiResponse:
        from vencertia.domain import CalibrationScope
        from vencertia.runtime.calibration_engine import CalibrationInput

        predictions = repo.list_predictions()
        try:
            cal_scope = CalibrationScope(scope.upper())
        except ValueError as exc:
            raise ValueError(f"invalid scope: {scope}") from exc
        profile = runtime.engines.calibration_engine.report(
            CalibrationInput(predictions, cal_scope, key, settings.ece_bins)
        )
        return ok(profile.model_dump(mode="json"))

    # -- review (v1.9 decision-review dashboard) -------------------------------------------

    @app.get("/v1/review", response_model=ApiResponse)
    def review(project_id: str | None = None) -> ApiResponse:
        """Read-only decision-review aggregation over existing ledgers.

        Combines the decision ledger (recommendation → action → outcome), the
        open predictions awaiting review, and the calibration overview into one
        payload for the review workbench. No engine recomputation, no writes.
        """
        from vencertia.domain import CalibrationScope
        from vencertia.presentation import review_summary
        from vencertia.runtime.calibration_engine import CalibrationInput

        records = repo.list_decision_records(project_id)
        # v1.9: enrich ledger rows with the human-readable decision question —
        # the raw option id is not a useful title for a review workbench.
        questions: dict[str, str] = {}
        for decision in repo.list_decisions(project_id):
            questions[decision.id] = decision.decision_question
        outcomes: list = []
        for r in records:
            outcomes.extend(repo.list_decision_outcome_records(r.id))
        open_preds = [p for p in repo.list_predictions(project_id) if p.is_open]
        profile = runtime.engines.calibration_engine.report(
            CalibrationInput(
                repo.list_predictions(), CalibrationScope("ALL"), "ALL", settings.ece_bins
            )
        )
        return ok(review_summary(records, outcomes, open_preds, profile, questions))

    # -- projects ------------------------------------------------------------------------

    @app.get("/v1/projects/{project_id}/beliefs", response_model=ApiResponse)
    def project_beliefs(project_id: str) -> ApiResponse:
        beliefs = repo.get_beliefs(project_id)
        return ok([b.model_dump(mode="json") for b in beliefs])

    @app.get("/v1/projects/{project_id}/critical-uncertainties", response_model=ApiResponse)
    def critical_uncertainties(project_id: str) -> ApiResponse:
        decisions = repo.list_decisions(project_id)
        if not decisions:
            return ok([])
        latest = max(decisions, key=lambda d: d.updated_at)
        beliefs = repo.get_beliefs(project_id)
        criticals = runtime.engines.uncertainty_engine.rank(latest, beliefs)
        return ok([c.model_dump(mode="json") for c in criticals])

    # -- v1.1: research ----------------------------------------------------------------

    @app.post("/v1/research/plan", response_model=ApiResponse)
    def research_plan(req: ResearchPlanRequest) -> ApiResponse:
        decision = repo.get_decision(req.decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", req.decision_id)
        beliefs = repo.get_beliefs(decision.project_id)
        criticals = runtime.engines.uncertainty_engine.rank(decision, beliefs)
        if runtime.engines.research_planner is None:
            raise ValueError("research_planner not wired")
        plan = runtime.engines.research_planner.plan(decision, beliefs, criticals, None)
        repo.save_research_plan(plan)
        return ok(plan.model_dump(mode="json"))

    @app.post("/v1/research/run", response_model=ApiResponse)
    def research_run(req: ResearchRunRequest) -> ApiResponse:
        """Execute the latest research plan through the SHARED pipeline (P0-5).

        v1.1.2 semantic upgrade: the endpoint now runs the full research
        pipeline (search → dedup → claim binding → applied evidence → belief
        updates → conflicts → stop rule) via ResearchExecutionService, instead
        of only storing traces. The response is additive: the previous trace
        list is preserved inside ``result.traces``.
        """
        decision = repo.get_decision(req.decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", req.decision_id)
        service = runtime.engines.research_execution
        if service is None:
            raise ValueError("research_execution not wired")
        result = service.run_plan(
            req.decision_id,
            question_ids=req.question_ids,
            max_queries=req.max_queries,
        )
        return ok(result.model_dump(mode="json"))

    @app.post("/v1/evidence/bind", response_model=ApiResponse)
    def evidence_bind(req: EvidenceBindRequest) -> ApiResponse:
        evidence = repo.get_evidence(req.evidence_id)
        if evidence is None:
            raise EntityNotFoundError("evidence", req.evidence_id)
        if runtime.engines.claim_binding_engine is None:
            raise ValueError("claim_binding_engine not wired")
        existing_claims = repo.list_claims()

        output = runtime.engines.claim_binding_engine.process(
            ClaimBindingInput(
                research_results=[
                    {
                        "evidence_id": evidence.id,
                        "id": evidence.id,
                        "scope": evidence.scope.value if hasattr(evidence.scope, "value") else evidence.scope,
                        "evidence_type": evidence.evidence_type.value
                        if hasattr(evidence.evidence_type, "value")
                        else evidence.evidence_type,
                        "source": evidence.source,
                        "supports_or_contradicts": evidence.supports_or_contradicts.value
                        if hasattr(evidence.supports_or_contradicts, "value")
                        else evidence.supports_or_contradicts,
                        "directness": evidence.directness,
                        "reliability": evidence.reliability,
                        "relevance": evidence.relevance,
                        "strength": evidence.strength,
                        "authority_level": evidence.authority_level.value
                        if hasattr(evidence.authority_level, "value")
                        else evidence.authority_level,
                        "verification": evidence.verification.value
                        if hasattr(evidence.verification, "value")
                        else evidence.verification,
                        "content_fingerprint": evidence.content_fingerprint,
                        "canonical_source_id": evidence.canonical_source_id,
                        "source_family": evidence.source_family,
                    }
                ],
                context={"claims": [c.model_dump(mode="json") for c in existing_claims]},
                existing_claims=[c.model_dump(mode="json") for c in existing_claims],
                auto_extract=req.auto_extract,
                binding_confidence_threshold=settings.binding_confidence_threshold,
            )
        )
        return ok(output.model_dump(mode="json"))

    @app.get("/v1/evidence/{evidence_id}/bindings", response_model=ApiResponse)
    def evidence_bindings(evidence_id: str) -> ApiResponse:
        bindings = repo.list_bindings(evidence_id=evidence_id)
        return ok([b.model_dump(mode="json") for b in bindings])

    @app.get("/v1/decisions/{decision_id}/sensitivity", response_model=ApiResponse)
    def decision_sensitivity(decision_id: str) -> ApiResponse:
        sensitivity = repo.get_decision_sensitivity(decision_id)
        if sensitivity is None:
            raise EntityNotFoundError("decision_sensitivity", decision_id)
        return ok(sensitivity.model_dump(mode="json"))

    @app.get("/v1/decisions/{decision_id}/trace", response_model=ApiResponse)
    def decision_trace(decision_id: str) -> ApiResponse:
        trace = repo.get_decision_trace(decision_id)
        if trace is None:
            raise EntityNotFoundError("decision_trace", decision_id)
        return ok(trace.model_dump(mode="json"))

    @app.get("/v1/beliefs/{belief_id}/history", response_model=ApiResponse)
    def belief_history(belief_id: str) -> ApiResponse:
        records = repo.list_belief_update_records(belief_id)
        return ok([r.model_dump(mode="json") for r in records])

    @app.get("/v1/research/{decision_id}/trace", response_model=ApiResponse)
    def research_trace(decision_id: str) -> ApiResponse:
        traces = repo.list_research_traces(decision_id)
        return ok([t.model_dump(mode="json") for t in traces])

    @app.post("/v1/claims/candidates/{candidate_id}/validate", response_model=ApiResponse)
    def validate_candidate(candidate_id: str) -> ApiResponse:
        candidates = repo.list_candidate_claims()
        candidate = next((c for c in candidates if c.id == candidate_id), None)
        if candidate is None:
            raise EntityNotFoundError("candidate_claim", candidate_id)

        updated = candidate.model_copy(update={"validation_status": "VALIDATED"})
        repo.save_candidate_claim(updated, expected_version=candidate.version)
        return ok(updated.model_dump(mode="json"))

    # -- v2.0: idea intake / business plan / skills --------------------------------

    @app.post("/v1/ideas/assess", response_model=ApiResponse)
    def idea_assess(req: IdeaAssessRequest) -> ApiResponse:
        """入口层：想法 → 结构化决策问题 + 假设清单 + 最大未知（只读评估，零持久化）。"""
        from vencertia.presentation import idea_summary
        from vencertia.runtime.idea_intake import IdeaIntakeService

        service = IdeaIntakeService(
            repo=repo,
            engines=runtime.engines,
            settings=settings,
            compiler=runtime.compiler,
            model=runtime.model,
        )
        assessment = service.assess(
            req.idea_text, domain=req.domain, user_id=req.user_id
        )
        return ok(idea_summary(assessment))

    @app.post("/v1/bp", response_model=ApiResponse)
    def business_plan(req: BpRequest) -> ApiResponse:
        """出口层：已持久化决策 → 商业计划（确定性骨架 + skill 叙事候选）。"""
        from vencertia.presentation import bp_markdown, bp_view
        from vencertia.runtime.bp_composer import BusinessPlanComposer

        composer = BusinessPlanComposer(repo=repo, engines=runtime.engines, settings=settings)
        plan = composer.compose(
            req.decision_id,
            company_name=req.company_name,
            tagline=req.tagline,
            market_note=req.market_note,
        )
        view = bp_view(plan)

        narratives: list[dict] = []
        traces: list[dict] = []
        if req.narrative:
            from vencertia.skills import SkillRouter, build_biz_skill_registry

            decision = repo.get_decision(req.decision_id)
            project_id = decision.project_id
            beliefs_ctx = []
            for b in repo.get_beliefs(project_id):
                beliefs_ctx.append(
                    {
                        "belief_id": b.id,
                        "claim_id": b.claim_id,
                        "statement": b.statement,
                        "scope": (
                            b.scope.value if hasattr(b.scope, "value") else str(b.scope)
                        ),
                        "probability": round(float(b.probability), 4),
                        "uncertainty": round(float(b.uncertainty), 4),
                        "evidence_count": len(
                            [
                                e
                                for e in repo.list_evidence(project_id=project_id)
                                if b.claim_id in e.claim_ids
                            ]
                        ),
                    }
                )
            context = {
                "claim_ids": [c.id for c in repo.list_claims(project_id)],
                "beliefs": beliefs_ctx,
                "assumptions": plan.assumption_register,
                "experiments": [
                    e.model_dump(mode="json")
                    for e in repo.list_experiments(project_id)
                    if (e.status.value if hasattr(e.status, "value") else str(e.status))
                    not in ("RESOLVED_SUPPORT", "RESOLVED_REFUTE", "RESOLVED_AMBIGUOUS")
                ],
                "decision": {
                    "decision_question": decision.decision_question,
                    "current_recommendation": decision.current_recommendation,
                    "status": decision.status,
                },
            }
            router = SkillRouter(build_biz_skill_registry(model=runtime.model))
            candidates, traces = router.run_stage("bp", context)
            narratives = [c.model_dump(mode="json") for c in candidates]
            traces = [t.model_dump(mode="json") for t in traces]
            if narratives:
                view["honest_notes"] = list(view["honest_notes"]) + [
                    f"叙事由 {len(narratives)} 个 V11 skill 生成（候选已过契约与引用校验，"
                    f"{sum(1 for t in traces if t['status'] == 'OK')} 通过 / "
                    f"{sum(1 for t in traces if t['status'] == 'REJECTED')} 拒绝）。"
                ]
        return ok(
            {
                "view": view,
                "markdown": bp_markdown(view),
                "narratives": narratives,
                "skill_traces": traces,
            }
        )

    @app.get("/v1/skills", response_model=ApiResponse)
    def list_skills() -> ApiResponse:
        """经验资产目录：版本化 skill 清单（谱系指向 legacy V11 源提示词）。"""
        from vencertia.skills import build_biz_skill_registry

        registry = build_biz_skill_registry(model=runtime.model)
        return ok([m.model_dump(mode="json") for m in registry.list()])

    # -- solve ----------------------------------------------------------------------------

    @app.post("/v1/solve", response_model=ApiResponse)
    def solve(
        req: SolveRequest,
        advanced: bool = False,
        view: Literal["full", "summary"] = "full",
    ) -> ApiResponse:
        result = runtime.solve(req)
        if view == "summary":
            from vencertia.presentation import solve_summary

            return ok(solve_summary(result))
        if not advanced:
            # V-7 Progressive Disclosure: Default returns the 5-section contract;
            # Advanced (?advanced=true) expands the structured advanced_view.
            result.advanced_view = None
        return ok(result.model_dump(mode="json"))

    # -- error handlers ---------------------------------------------------------------------

    _register_exception_handlers(app, fail)

    # -- static UI (v1.8) ----------------------------------------------------------------
    # Zero-build decision workbench served by FastAPI; the frontend reuses the
    # already-computed Chinese projection layer over /v1/solve.
    import pathlib

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    ui_dir = pathlib.Path(__file__).parent / "ui"
    app.mount("/static", StaticFiles(directory=str(ui_dir)), name="ui-static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(ui_dir / "index.html")

    return app


# -- module-level app (lazy) ----------------------------------------------------
# v1.9: the ``app`` singleton is built on FIRST ATTRIBUTE ACCESS instead of at
# import time. ``uvicorn vencertia.api:app`` and ``from vencertia.api import
# app`` both trigger attribute lookup, so the documented run path is unchanged;
# importing the module for ``create_app`` (tests, tooling) no longer pays the
# side effect of constructing a repository + opening a database connection.
_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        global _app
        if _app is None:
            _app = build_container().fastapi_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
