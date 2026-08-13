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

    from vencertia.runtime.presentation import localize_error_message

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
        from vencertia.events.types import EventType, make_event

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

    # -- solve ----------------------------------------------------------------------------

    @app.post("/v1/solve", response_model=ApiResponse)
    def solve(
        req: SolveRequest,
        advanced: bool = False,
        view: Literal["full", "summary"] = "full",
    ) -> ApiResponse:
        result = runtime.solve(req)
        if view == "summary":
            from vencertia.runtime.presentation import solve_summary

            return ok(solve_summary(result))
        if not advanced:
            # V-7 Progressive Disclosure: Default returns the 5-section contract;
            # Advanced (?advanced=true) expands the structured advanced_view.
            result.advanced_view = None
        return ok(result.model_dump(mode="json"))

    # -- error handlers ---------------------------------------------------------------------

    _register_exception_handlers(app, fail)

    return app


_container = build_container()
app = _container.fastapi_app()
