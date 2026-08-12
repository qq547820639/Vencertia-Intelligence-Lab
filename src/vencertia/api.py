"""Vencertia v1.0 REST API (FastAPI).

Unified response envelope: ``{"code": 0, "data": ..., "message": "ok"}``.
Domain errors: EntityNotFoundError -> 404, StaleWriteError -> 409,
ValueError -> 400.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Action,
    Belief,
    Decision,
    DecisionOption,
    Evidence,
    Experiment,
    Outcome,
    OutcomeType,
    PredictionEntry,
    Project,
    VencertiaBaseModel,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.base import EntityNotFoundError, Repository, StaleWriteError
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, SolveResult, default_engine_bundle
from vencertia.runtime.evidence_policy import EvidencePolicy


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


class OutcomeRequest(VencertiaBaseModel):
    action_id: str
    result: str
    quantitative: Dict[str, float] = Field(default_factory=dict)
    outcome_type: OutcomeType | str = OutcomeType.PARTIAL
    direction: str | None = None


class ExperimentProposeRequest(VencertiaBaseModel):
    decision_id: str
    candidates: list[Experiment] = Field(default_factory=list)
    max_results: int = 5


class ExperimentResolveRequest(VencertiaBaseModel):
    result: str
    outcome_type: OutcomeType | str = OutcomeType.PARTIAL
    quantitative: Dict[str, float] = Field(default_factory=dict)


class PredictionCreateRequest(VencertiaBaseModel):
    decision_id: str


class PredictionResolveRequest(VencertiaBaseModel):
    outcome: bool


class CalibrationQuery(BaseModel):
    scope: str = "ALL"
    key: str = "ALL"


def create_app(
    settings: Settings,
    repo: Repository,
    runtime: SolveOrchestrator,
) -> FastAPI:
    app = FastAPI(title="Vencertia Decision Runtime", version="1.0.0")

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
                "version": "1.0.0",
                "policy_version": settings.policy_version,
                "model_provider": settings.model_provider,
            }
        )

    # -- decisions -------------------------------------------------------------

    @app.post("/v1/decisions/compile", response_model=ApiResponse)
    def compile_decision(req: CompileRequest) -> ApiResponse:
        try:
            project = repo.get_project(req.project_id)
            if project is None:
                raise EntityNotFoundError("project", req.project_id)
            compiled = runtime.compiler.compile(
                req.problem_text,
                {"project_id": req.project_id, "user_id": req.user_id or project.user_id},
                options=req.options,
            )
            return ok(compiled.model_dump(mode="json"))
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/decisions/evaluate", response_model=ApiResponse)
    def evaluate_decision(req: EvaluateRequest) -> ApiResponse:
        try:
            result, convergence = runtime.evaluate_decision(req.decision_id)
            return ok(
                {
                    "decision": result.model_dump(mode="json"),
                    "convergence": convergence.model_dump(mode="json"),
                }
            )
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/decisions/{decision_id}", response_model=ApiResponse)
    def get_decision(decision_id: str) -> ApiResponse:
        decision = repo.get_decision(decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail=f"decision not found: {decision_id}")
        return ok(decision.model_dump(mode="json"))

    # -- evidence ----------------------------------------------------------------

    @app.post("/v1/evidence", response_model=ApiResponse)
    def add_evidence(req: EvidenceRequest) -> ApiResponse:
        grade = runtime.policy.grade(req.evidence)
        if grade.scope_gate == "REJECTED":
            raise HTTPException(status_code=400, detail=grade.reason)
        graded = runtime.policy.apply_authority(req.evidence, settings.policy_version)
        repo.add_evidence(graded)
        return ok(graded.model_dump(mode="json"), message=grade.reason)

    # -- outcomes ----------------------------------------------------------------

    @app.post("/v1/outcomes", response_model=ApiResponse)
    def record_outcome(req: OutcomeRequest) -> ApiResponse:
        try:
            result = runtime.record_outcome(
                req.action_id,
                req.result,
                quantitative=req.quantitative,
                outcome_type=req.outcome_type,
                direction=req.direction,
            )
            return ok(result.model_dump(mode="json"))
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # -- experiments ---------------------------------------------------------------

    @app.post("/v1/experiments/propose", response_model=ApiResponse)
    def propose_experiment(req: ExperimentProposeRequest) -> ApiResponse:
        decision = repo.get_decision(req.decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail=f"decision not found: {req.decision_id}")
        beliefs = repo.get_beliefs(decision.project_id)
        criticals = runtime.engines.uncertainty_engine.rank(decision, beliefs)
        critical_belief_id = criticals[0].belief_id if criticals else None
        proposal = runtime.engines.experiment_optimizer.propose(
            __import__("vencertia.runtime.experiment_optimizer", fromlist=["ExperimentProposalInput"]).ExperimentProposalInput(
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
            }
        )

    @app.post("/v1/experiments/{experiment_id}/resolve", response_model=ApiResponse)
    def resolve_experiment(experiment_id: str, req: ExperimentResolveRequest) -> ApiResponse:
        experiment = repo.get_experiment(experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail=f"experiment not found: {experiment_id}")
        action = Action(
            id=f"ACT_{experiment_id}",
            project_id="PRJ_UNKNOWN",
            kind="EXPERIMENT",
            description=experiment.action,
            decision_id=experiment.decision_id,
            experiment_id=experiment.id,
            status="RUNNING",
        )
        # Find the decision's project to attach the action correctly.
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
            raise HTTPException(status_code=404, detail=f"decision not found: {req.decision_id}")
        beliefs = repo.get_beliefs(decision.project_id)
        entries = runtime.engines.prediction_ledger.register(decision, beliefs)
        return ok([e.model_dump(mode="json") for e in entries])

    @app.post("/v1/predictions/{prediction_id}/resolve", response_model=ApiResponse)
    def resolve_prediction(prediction_id: str, req: PredictionResolveRequest) -> ApiResponse:
        try:
            entry = runtime.engines.prediction_ledger.resolve(prediction_id, req.outcome)
            return ok(entry.model_dump(mode="json"))
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- calibration -------------------------------------------------------------------

    @app.get("/v1/calibration", response_model=ApiResponse)
    def calibration_report(scope: str = "ALL", key: str = "ALL") -> ApiResponse:
        from vencertia.domain import CalibrationScope
        from vencertia.runtime.calibration_engine import CalibrationInput

        predictions = repo.list_predictions()
        try:
            cal_scope = CalibrationScope(scope.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid scope: {scope}")
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

    # -- solve ----------------------------------------------------------------------------

    @app.post("/v1/solve", response_model=ApiResponse)
    def solve(req: SolveRequest) -> ApiResponse:
        try:
            result = runtime.solve(req)
            return ok(result.model_dump(mode="json"))
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- error handlers ---------------------------------------------------------------------

    @app.exception_handler(StaleWriteError)
    async def stale_write_handler(_, exc: StaleWriteError):
        return __import__("fastapi.responses", fromlist=["JSONResponse"]).JSONResponse(
            status_code=409,
            content=fail(409, str(exc)).model_dump(mode="json"),
        )

    return app


def default_runtime(
    settings: Settings | None = None,
    repo: Repository | None = None,
) -> SolveOrchestrator:
    """Build the default offline runtime (mock providers, SQLite)."""
    cfg = settings or get_settings()
    repository = repo or SQLiteRepository(cfg.db_dsn)
    bus = EventBus(sink=repository.append_event)
    engines = default_engine_bundle(repository, cfg, bus)
    return SolveOrchestrator(
        repo=repository,
        policy=engines.evidence_policy,
        engines=engines,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
        bus=bus,
        settings=cfg,
    )


_settings = get_settings()
_repo = SQLiteRepository(_settings.db_dsn)
app = create_app(_settings, _repo, default_runtime(_settings, _repo))
