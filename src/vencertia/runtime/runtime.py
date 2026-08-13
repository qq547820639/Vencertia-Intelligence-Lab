"""SolveOrchestrator — deterministic state-mutation entry point (ADR-002).

v1.1 flow (design §3.4): Context → Compiler → Critical Unknowns →
ResearchPlanner → ResearchRun → ClaimBinding → EvidencePolicy → BeliefUpdate →
ResearchStopCheck → Uncertainty → Convergence → Decision+Trace → Sensitivity →
(ABSTAIN/not converged → ExperimentOptimizer) → PredictionLedger → Persist.

v1.0 invariants are preserved: deterministic runtime owns state; capability
output is always candidate → validation → persistence; ABSTAIN always carries a
next experiment; predictions are registered before settlement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import Field

from vencertia.capabilities import ChallengerCapability, CompiledDecision, DecisionCompiler
from vencertia.config import Settings, get_settings
from vencertia.domain import (
    ActionState,
    Belief,
    CalibratedConfidence,
    ClaimBindingInput,
    ConvergenceReport,
    CriticalUncertainty,
    Decision,
    DecisionOption,
    DecisionRecord,
    DecisionResult,
    DecisionSensitivity,
    DecisionTrace,
    Direction,
    Evidence,
    EvidenceConflict,
    Experiment,
    ModelCriticGate,
    ModelCritique,
    Outcome,
    OutcomeType,
    PredictionEntry,
    Project,
    ProjectStatus,
    RankedExperiment,
    ResearchPlan,
    ResearchStopReport,
    ResearchTrace,
    SolveMode,
    Stage,
    VencertiaBaseModel,
    map_decision_type_to_action_state,
    utcnow,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.providers.models import ModelProvider, RetrievalProvider, SearchProvider
from vencertia.repositories.base import EntityNotFoundError, Repository
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.calibration_engine import CalibrationEngine
from vencertia.runtime.claim_binding import (
    ClaimBindingEngine,
    ClaimExtractor,
    DeterministicClaimMatcher,
    EvidenceClaimLinker,
)
from vencertia.runtime.confidence_calibrator import ConfidenceCalibrator
from vencertia.runtime.conflict_engine import ConflictEngine
from vencertia.runtime.context import ContextBuilder, ContextBundle
from vencertia.runtime.context_ranker import (
    ContextRanker,
    DecisionRelevantContextBuilder,
)
from vencertia.runtime.convergence_engine import ConvergenceEngine
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput
from vencertia.runtime.decision_sensitivity import DecisionSensitivityEngine
from vencertia.runtime.evidence_dedup import EvidenceDedupEngine
from vencertia.runtime.evidence_policy import EvidencePolicy
from vencertia.runtime.experiment_optimizer import (
    ExperimentOptimizer,
    ExperimentProposalInput,
)
from vencertia.runtime.observability import CallRecorder
from vencertia.runtime.opportunity_cost import OpportunityCostEngine
from vencertia.runtime.prediction_ledger import PredictionLedger
from vencertia.runtime.research_planner import ResearchPlanner
from vencertia.runtime.research_service import (
    ResearchExecutionService,
)
from vencertia.runtime.research_service import (
    evidence_to_result as _research_evidence_to_result,
)
from vencertia.runtime.research_stop import ResearchStopRule
from vencertia.runtime.uncertainty_engine import UncertaintyEngine


class SolveRequest(VencertiaBaseModel):
    project_id: str
    problem_text: str
    options: list[DecisionOption] | None = None
    experiment_candidates: list[Experiment] = Field(default_factory=list)
    risk_aversion: float | None = None
    minimum_margin: float | None = None
    max_critical_uncertainty: float | None = None
    user_id: str | None = None
    domain: str = "general"
    model_tag: str = "mock"
    mode: SolveMode | None = None  # V-7: EXPLORE/OPERATE; None = compatible default


class SolveResult(VencertiaBaseModel):
    decision: DecisionResult
    decision_id: str
    convergence: ConvergenceReport
    critical_uncertainties: list[CriticalUncertainty] = Field(default_factory=list)
    next_experiment: RankedExperiment | None = None
    predictions: list[PredictionEntry] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class SolveResultAdvancedView(VencertiaBaseModel):
    """V-7 advanced projection (structured sub-model, not a throwaway dict)."""

    belief_graph: list[dict] = Field(default_factory=list)  # BeliefEdge JSON projection
    utility: dict[str, float] = Field(default_factory=dict)  # option_id -> adjusted_utility
    sensitivity: DecisionSensitivity | None = None
    trace: DecisionTrace | None = None
    stakes: dict | None = None  # StakesProfile projection


class SolveResultV11(SolveResult):
    """v1.1 extended solve output (all new fields optional, backward compatible)."""

    confidence_calibrated: CalibratedConfidence | None = None
    why: DecisionTrace | None = None
    belief_snapshot: list[dict] = Field(default_factory=list)
    what_could_change_my_mind: list[str] = Field(default_factory=list)
    robustness: str | None = None
    research_performed: list[ResearchTrace] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    evidence_rejected: list[dict] = Field(default_factory=list)
    success_criteria: str | None = None
    failure_criteria: str | None = None
    stop_condition: str | None = None
    sensitivity: DecisionSensitivity | None = None
    # V-7 presentation-layer mapping + mode echo + advanced projection.
    action_state: ActionState | None = None
    mode: SolveMode | None = None
    advanced_view: SolveResultAdvancedView | None = None
    # V-3 (T3 wiring): structured model critique, optional, default None.
    model_critique: ModelCritique | None = None


class OutcomeRecordedResult(VencertiaBaseModel):
    outcome: Outcome
    outcome_evidence: Evidence
    belief_deltas: list[Belief] = Field(default_factory=list)
    decision_update: DecisionResult | None = None
    convergence: ConvergenceReport | None = None
    calibration_delta: dict[str, Any] | None = None
    predictions_resolved: list[PredictionEntry] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


@dataclass
class EngineBundle:
    """All deterministic engines + ledger + context builders (v1.0 + v1.1)."""

    evidence_policy: EvidencePolicy
    belief_engine: BeliefEngine
    uncertainty_engine: UncertaintyEngine
    decision_engine: DecisionEngine
    convergence_engine: ConvergenceEngine
    experiment_optimizer: ExperimentOptimizer
    prediction_ledger: PredictionLedger
    calibration_engine: CalibrationEngine
    opportunity_cost: OpportunityCostEngine
    context_builder: ContextBuilder
    # v1.1 engines (optional so v1.0 callers keep working)
    context_builder_v11: DecisionRelevantContextBuilder | None = None
    claim_binding_engine: ClaimBindingEngine | None = None
    research_planner: ResearchPlanner | None = None
    research_stop_rule: ResearchStopRule | None = None
    dedup_engine: EvidenceDedupEngine | None = None
    conflict_engine: ConflictEngine | None = None
    decision_sensitivity_engine: DecisionSensitivityEngine | None = None
    confidence_calibrator: ConfidenceCalibrator | None = None
    call_recorder: CallRecorder | None = None
    research_execution: Any | None = None  # ResearchExecutionService (P0-5)
    # v1.1.2 extracted services (P2-16; additive, set by default_engine_bundle)
    compilation_service: Any | None = None
    decision_evaluation_service: Any | None = None
    outcome_settlement_service: Any | None = None


def default_engine_bundle(
    repo: Repository,
    settings: Settings | None = None,
    bus: EventBus | None = None,
) -> EngineBundle:
    """Build a fully-wired EngineBundle (v1.0 + v1.1) for a repository."""
    cfg = settings or get_settings()
    policy = EvidencePolicy(cfg)
    belief_engine = BeliefEngine(cfg, policy)
    uncertainty_engine = UncertaintyEngine()
    decision_engine = DecisionEngine(cfg, uncertainty_engine)
    convergence_engine = ConvergenceEngine(cfg)
    experiment_optimizer = ExperimentOptimizer(cfg)
    prediction_ledger = PredictionLedger(repo, cfg)
    calibration_engine = CalibrationEngine(cfg, bus)
    opportunity_cost = OpportunityCostEngine(repo, cfg)
    context_builder = ContextBuilder(repo)
    ranker = ContextRanker(cfg)
    context_builder_v11 = DecisionRelevantContextBuilder(repo, ranker=ranker)
    claim_binding_engine = ClaimBindingEngine(
        extractor=ClaimExtractor(settings=cfg),
        matcher=DeterministicClaimMatcher(cfg),
        linker=EvidenceClaimLinker(),
        policy=policy,
        repo=repo,
        bus=bus,
        settings=cfg,
    )
    research_planner = ResearchPlanner(settings=cfg, repo=repo)
    research_stop_rule = ResearchStopRule(settings=cfg)
    dedup_engine = EvidenceDedupEngine(settings=cfg)
    conflict_engine = ConflictEngine(cfg)
    decision_sensitivity_engine = DecisionSensitivityEngine(cfg)
    confidence_calibrator = ConfidenceCalibrator(
        calibration_engine=calibration_engine, repo=repo, settings=cfg
    )
    call_recorder = CallRecorder(repo, enabled=cfg.call_log_enabled, settings=cfg)
    bundle = EngineBundle(
        evidence_policy=policy,
        belief_engine=belief_engine,
        uncertainty_engine=uncertainty_engine,
        decision_engine=decision_engine,
        convergence_engine=convergence_engine,
        experiment_optimizer=experiment_optimizer,
        prediction_ledger=prediction_ledger,
        calibration_engine=calibration_engine,
        opportunity_cost=opportunity_cost,
        context_builder=context_builder,
        context_builder_v11=context_builder_v11,
        claim_binding_engine=claim_binding_engine,
        research_planner=research_planner,
        research_stop_rule=research_stop_rule,
        dedup_engine=dedup_engine,
        conflict_engine=conflict_engine,
        decision_sensitivity_engine=decision_sensitivity_engine,
        confidence_calibrator=confidence_calibrator,
        call_recorder=call_recorder,
    )
    bundle.research_execution = ResearchExecutionService(
        repo=repo,
        engines=bundle,
        policy=policy,
        settings=cfg,
        bus=bus,
    )
    # v1.1.2 (P2-16): extracted services (additive; facade delegates).
    from vencertia.runtime.compilation_service import CompilationService
    from vencertia.runtime.decision_evaluation_service import DecisionEvaluationService
    from vencertia.runtime.outcome_settlement_service import OutcomeSettlementService

    bundle.compilation_service = CompilationService(
        repo=repo, engines=bundle, settings=cfg, bus=bus
    )
    bundle.decision_evaluation_service = DecisionEvaluationService(
        repo=repo, engines=bundle, settings=cfg, bus=bus
    )
    bundle.outcome_settlement_service = OutcomeSettlementService(
        repo=repo, engines=bundle, policy=policy, settings=cfg, bus=bus
    )
    return bundle


class SolveOrchestrator:
    """Facade orchestrating the deterministic decision loop."""

    def __init__(
        self,
        repo: Repository,
        policy: EvidencePolicy | None = None,
        engines: EngineBundle | None = None,
        model: ModelProvider | None = None,
        search: SearchProvider | None = None,
        retrieval: RetrievalProvider | None = None,
        bus: EventBus | None = None,
        settings: Settings | None = None,
        compiler: DecisionCompiler | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repo = repo
        self.bus = bus or EventBus(sink=repo.append_event)
        self.policy = policy or EvidencePolicy(self.settings)
        self.engines = engines or default_engine_bundle(repo, self.settings, self.bus)
        self.model = model
        self.search = search
        self.retrieval = retrieval
        # P0-5: keep the shared ResearchExecutionService in sync with the
        # providers this orchestrator was wired with.
        if self.engines.research_execution is not None:
            self.engines.research_execution.model = self.model
            self.engines.research_execution.search = self.search
            self.engines.research_execution.retrieval = self.retrieval
        elif model is not None or search is not None or retrieval is not None:
            from vencertia.runtime.research_service import ResearchExecutionService

            self.engines.research_execution = ResearchExecutionService(
                repo=self.repo,
                engines=self.engines,
                policy=self.policy,
                settings=self.settings,
                bus=self.bus,
                model=self.model,
                search=self.search,
                retrieval=self.retrieval,
            )
        if compiler is not None:
            self.compiler = compiler
        elif model is not None:
            from vencertia.capabilities import DecisionCompiler

            self.compiler = DecisionCompiler(model=model, settings=self.settings, repo=self.repo)
        else:
            self.compiler = None

    # -- event helpers ---------------------------------------------------------

    def _emit(
        self,
        event_type: EventType,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.bus.publish(make_event(event_type, entity_type, entity_id, payload))

    # -- model critic (V-3 gate wiring) ---------------------------------------

    def _run_model_critic(self, decision: Decision, context) -> ModelCritique | None:
        """Run the challenger model critic only when the gate requires it.

        Failure or a None critique degrades gracefully (warn + PROVIDER_FAILED
        event) — the solve loop never blocks on the critic.
        """
        stakes_class = (
            decision.stakes_class.value
            if hasattr(decision.stakes_class, "value")
            else str(decision.stakes_class)
        )
        if not ModelCriticGate.should_require(stakes_class, self.settings.critic_required_stakes):
            return None
        try:
            result = ChallengerCapability().run("critique this decision", context)
            critique = result.critique if result else None
        except Exception as exc:  # degrade: a real LLM failure must not block solve
            logging.getLogger("vencertia").warning("Model critic unavailable: %s", exc)
            self._emit(
                EventType.PROVIDER_FAILED,
                "model_critic",
                decision.id,
                {"reason": str(exc)},
            )
            critique = None
        if critique is None:
            logging.getLogger("vencertia").warning(
                "Model critic returned no critique; proceeding without it"
            )
        return critique

    # -- solve ----------------------------------------------------------------

    def solve(self, request: SolveRequest) -> SolveResult:
        project = self._load_or_create_project(request.project_id, request.user_id)
        pre_context = self._build_context(project, request)
        compiled = self._compile(request, project, pre_context)
        self._persist_compiled(compiled, request)
        decision = compiled.decision

        # Rebuild context after persisting compiled claims/beliefs so the
        # research pipeline sees real claims to bind against. P0-1: pass the
        # CURRENT decision so decision-relevance ranking is not decision-blind
        # before the decision row is persisted.
        context = self._build_context(project, request, decision=compiled.decision)

        beliefs = self.repo.get_beliefs(project.id)
        traces: list[ResearchTrace] = []
        stop_report: ResearchStopReport | None = None
        research_plan: ResearchPlan | None = None
        all_applied: list[Evidence] = []
        rejected_evidence: list[dict] = []

        criticals = self.engines.uncertainty_engine.rank(decision, beliefs)

        # ---- plan research ---------------------------------------------------
        if self.engines.research_planner is not None:
            research_plan = self.engines.research_planner.plan(decision, beliefs, criticals, context)
            if research_plan.questions:
                self.repo.save_research_plan(research_plan)
                self._emit(
                    EventType.RESEARCH_PLANNED,
                    "research_plan",
                    research_plan.id,
                    {"question_count": len(research_plan.questions)},
                )

        # ---- research loop ----------------------------------------------------
        if research_plan is not None and research_plan.questions:
            for round_no in range(1, self.settings.research_max_rounds + 1):
                self._emit(
                    EventType.RESEARCH_STARTED,
                    "research",
                    research_plan.id,
                    {"round": round_no},
                )
                beliefs_before = self.repo.get_beliefs(project.id)
                if self.engines.research_execution is not None:
                    trace, candidates = self.engines.research_execution.run_solve_round(
                        request, project, decision, research_plan, round_no
                    )
                else:
                    trace, candidates = self._run_research_round(
                        request, project, decision, research_plan, round_no
                    )
                traces.append(trace)

                # P2-17: the per-round deterministic mutation batch is ATOMIC.
                state: dict = {}
                # Bind loop variables as default args: the closure runs
                # synchronously inside in_transaction and must capture THIS
                # iteration's values (ruff B023).
                def _round_batch(
                    _state=state,
                    _trace=trace,
                    _candidates=candidates,
                    _round_no=round_no,
                    _beliefs_before=beliefs_before,
                    _beliefs=beliefs,
                ) -> None:
                    kept = _candidates
                    if self.engines.dedup_engine is not None:
                        dedup = self.engines.dedup_engine.group(_candidates)
                        _trace.duplicate_dropped = len(dedup.dropped_ids)
                        kept_ids = set(dedup.kept_ids)
                        kept = [c for c in _candidates if c.id in kept_ids]
                    # Drop candidates whose content was already applied in an
                    # earlier round (same fingerprint) — do not re-apply twice.
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

                    applied_local: list[Evidence] = []
                    round_bindings_local: list = []
                    if self.engines.claim_binding_engine is not None:
                        binding_output = self.engines.claim_binding_engine.process(
                            ClaimBindingInput(
                                research_results=[self._evidence_to_result(e) for e in kept],
                                context=context,
                                existing_claims=self.repo.list_claims(project.id),
                                auto_extract=True,
                                binding_confidence_threshold=self.settings.binding_confidence_threshold,
                            )
                        )
                        applied_local = [
                            Evidence.model_validate(e) for e in binding_output.applied_evidence
                        ]
                        _state["rejected"] = list(binding_output.rejected_evidence)
                        _trace.new_evidence_ids = [e.id for e in applied_local]
                        round_bindings_local = list(binding_output.bindings) + list(
                            binding_output.unbound
                        )

                    # ---- conflict + belief update ----------------------------------
                    conflicts_local: list[EvidenceConflict] = []
                    cumulative = list(all_applied) + applied_local
                    if applied_local and self.engines.conflict_engine is not None:
                        evidence_by_claim: dict[str, list[Evidence]] = {}
                        for evidence in cumulative:
                            for cid in evidence.claim_ids:
                                evidence_by_claim.setdefault(cid, []).append(evidence)
                        conflicts_local = self.engines.conflict_engine.detect(evidence_by_claim)
                        for conflict in conflicts_local:
                            self.repo.save_evidence_conflict(conflict)

                    beliefs_for_update = self.repo.get_beliefs(project.id)
                    if applied_local:
                        updated_output = self.engines.belief_engine.update(
                            BeliefUpdateInput(
                                beliefs=beliefs_for_update,
                                evidence=applied_local,
                                policy=self.policy,
                                max_pseudo_observations=self.settings.max_pseudo_observations,
                                conflict_weight_threshold=self.settings.conflict_weight_threshold,
                            )
                        )
                        # Apply conflict uncertainty raises.
                        raise_by_claim: dict[str, float] = {}
                        for conflict in conflicts_local:
                            raise_by_claim[conflict.claim_id] = round(
                                min(1.0, 0.15 * conflict.severity), 6
                            )
                        for belief in updated_output.beliefs:
                            if belief.claim_id in raise_by_claim:
                                new_uncertainty = round(
                                    min(1.0, belief.uncertainty + raise_by_claim[belief.claim_id]), 6
                                )
                                object.__setattr__(belief, "uncertainty", new_uncertainty)
                                object.__setattr__(
                                    belief, "confidence", max(0.0, min(1.0, 1.0 - new_uncertainty))
                                )
                        self._save_beliefs(updated_output.beliefs, batch_id=_trace.id)
                        self._save_belief_update_records(updated_output, conflicts_local)
                        _state["beliefs"] = self.repo.get_beliefs(project.id)

                    # ---- stop check ------------------------------------------------
                    target_claims_local = [
                        b.claim_id for b in (_state.get("beliefs") or self.repo.get_beliefs(project.id))
                    ]
                    stop_local = None
                    if self.engines.research_stop_rule is not None:
                        from vencertia.runtime.research_stop import RoundSummary

                        latency_ms = 0.0
                        if _trace.completed_at is not None and _trace.started_at is not None:
                            latency_ms = (
                                _trace.completed_at - _trace.started_at
                            ).total_seconds() * 1000.0
                        # M0-2: real decision_sensitivity_signal — feed the
                        # recommendation before/after this round's belief update.
                        beliefs_now = self.repo.get_beliefs(project.id) or _beliefs
                        decision_result_before = None
                        decision_result_after = None
                        if decision is not None and len(decision.options) >= 2:
                            try:
                                decision_result_before = self.engines.decision_engine.evaluate(
                                    DecisionEngineInput(
                                        decision=decision,
                                        beliefs=_beliefs_before,
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
                        round_summary = RoundSummary(
                            applied_evidence=applied_local,
                            bindings=list(round_bindings_local),
                            target_claim_ids=target_claims_local,
                            beliefs_before=_beliefs_before,
                            beliefs_after=beliefs_now,
                            decision_result_before=decision_result_before,
                            decision_result_after=decision_result_after,
                            queries_executed=_trace.queries_executed,
                            latency_ms=latency_ms,
                        )
                        stop_local = self.engines.research_stop_rule.evaluate(
                            traces,
                            _beliefs_before,
                            self.repo.get_beliefs(project.id) or _beliefs,
                            target_claims_local,
                            decision=decision,
                            round_no=_round_no,
                            round_summary=round_summary,
                        )
                        _trace.stop_status = stop_local.status
                        _trace.stop_reason = stop_local.reason
                    _state["stop_report"] = stop_local
                    _state["applied"] = applied_local
                    _state["conflicts"] = conflicts_local
                    _state["round_bindings"] = round_bindings_local
                    self.repo.save_research_trace(_trace)

                self.repo.in_transaction(_round_batch)
                applied = state.get("applied", [])
                stop_report = state.get("stop_report")
                if state.get("rejected"):
                    rejected_evidence.extend(state["rejected"])
                all_applied.extend(applied)
                if state.get("beliefs"):
                    beliefs = state["beliefs"]
                self._emit(
                    EventType.RESEARCH_COMPLETED,
                    "research_trace",
                    trace.id,
                    {"status": trace.stop_status},
                )
                if stop_report is not None and stop_report.status != "RESEARCH_MORE":
                    self._emit(
                        EventType.RESEARCH_EXHAUSTED,
                        "research",
                        research_plan.id,
                        {"status": stop_report.status, "reason": stop_report.reason},
                    )
                    break

        # ---- post-research pipeline -------------------------------------------
        beliefs = self.repo.get_beliefs(project.id) or beliefs
        criticals = self.engines.uncertainty_engine.rank(decision, beliefs)
        experiments = compiled.experiments or request.experiment_candidates

        # V-3 (T3): run the model critic BEFORE decision evaluation when the
        # gate requires it. Failure/None degrades to proceeding without a
        # critique (never blocks solve).
        model_critique = self._run_model_critic(decision, context)

        # P2-16: convergence + decision engine + trace + sensitivity delegated
        # to DecisionEvaluationService (behavior identical to v1.1.1 inline).
        if self.engines.decision_evaluation_service is not None:
            decision_result, convergence, decision_trace, sensitivity = (
                self.engines.decision_evaluation_service.evaluate(
                    decision,
                    beliefs,
                    risk_aversion=request.risk_aversion,
                    minimum_margin=request.minimum_margin,
                    max_critical_uncertainty=request.max_critical_uncertainty,
                    experiments=experiments,
                    research_stop_status=stop_report.status if stop_report else None,
                )
            )
        else:
            pre_convergence = self.engines.convergence_engine.check(
                decision,
                beliefs,
                criticals,
                experiments=experiments,
                research_stop_status=stop_report.status if stop_report else None,
            )
            decision_result = self.engines.decision_engine.evaluate(
                DecisionEngineInput(
                    decision=decision,
                    beliefs=beliefs,
                    risk_aversion=request.risk_aversion or self.settings.risk_aversion,
                    minimum_margin=request.minimum_margin or self.settings.minimum_margin,
                    max_critical_uncertainty=(
                        request.max_critical_uncertainty or self.settings.max_critical_uncertainty
                    ),
                    convergence_status=pre_convergence.status,
                    convergence_reason=pre_convergence.reason,
                )
            )

            if decision_result.status == "ABSTAIN":
                convergence = pre_convergence
            else:
                convergence = self.engines.convergence_engine.check(
                    decision,
                    beliefs,
                    criticals,
                    experiments=experiments,
                    decision_status=decision_result.status,
                    research_stop_status=stop_report.status if stop_report else None,
                )

            # ---- decision trace + sensitivity -------------------------------------
            decision_trace = self.engines.decision_engine.build_trace(
                DecisionEngineInput(
                    decision=decision,
                    beliefs=beliefs,
                    risk_aversion=request.risk_aversion or self.settings.risk_aversion,
                    minimum_margin=request.minimum_margin or self.settings.minimum_margin,
                    max_critical_uncertainty=(
                        request.max_critical_uncertainty or self.settings.max_critical_uncertainty
                    ),
                    convergence_status=pre_convergence.status,
                    convergence_reason=pre_convergence.reason,
                ),
                decision_result,
            )
            self.repo.save_decision_trace(decision_trace)

            sensitivity: DecisionSensitivity | None = None
            if self.engines.decision_sensitivity_engine is not None:
                sensitivity = self.engines.decision_sensitivity_engine.compute(
                    decision, beliefs, decision_result
                )
                self.repo.save_decision_sensitivity(sensitivity)
                self._emit(
                    EventType.DECISION_SENSITIVITY_COMPUTED,
                    "decision",
                    decision.id,
                    {"robustness": sensitivity.robustness, "flips": len(sensitivity.flips)},
                )

        next_experiment: RankedExperiment | None = None
        if decision_result.status == "ABSTAIN":
            proposal = self.engines.experiment_optimizer.propose(
                ExperimentProposalInput(
                    decision=decision,
                    beliefs=beliefs,
                    critical_belief_id=decision_result.critical_belief_id,
                    candidates=experiments,
                    max_results=self.settings.experiment_max_results,
                )
            )
            # P0-6: rejected experiments are surfaced in the decision trace and
            # rationale (they were validated inside propose()).
            if proposal.rejected:
                rejected_note = (
                    "Rejected experiments: "
                    + "; ".join(
                        f"{r.get('name') or r.get('experiment_id')} "
                        f"({', '.join(r.get('reasons') or [])})"
                        for r in proposal.rejected
                    )
                )
                decision_trace.notes.append(rejected_note)
            if proposal.ranked:
                next_experiment = proposal.ranked[0]
            else:
                # Invariant (ADR-007): ABSTAIN must always carry a next
                # experiment. The default must itself pass the SAME validator
                # (P0-6); if it somehow does not (defensive), we still emit the
                # synthesized default so ABSTAIN never loses next_experiment,
                # but the validator failure is recorded in the trace.
                default = self._synthesize_default_experiment(
                    decision, decision_result.critical_belief_id
                )
                from vencertia.runtime.experiment_optimizer import validate_experiment

                v = validate_experiment(default)
                if not v.valid:
                    decision_trace.notes.append(
                        f"default experiment failed validation: {v.reasons}"
                    )
                next_experiment = RankedExperiment(experiment=default, priority_score=0.0)
            self.repo.save_experiment(next_experiment.experiment)
            self._emit(
                EventType.EXPERIMENT_PROPOSED,
                "experiment",
                next_experiment.experiment.id,
                {"priority_score": next_experiment.priority_score},
            )
            if convergence.status == "SEARCH_EXHAUSTED":
                convergence = convergence.model_copy(
                    update={
                        "status": "EXPERIMENT_REQUIRED",
                        "reason": (
                            "Research exhausted, but an executable experiment is "
                            "available; run it before committing."
                        ),
                        "next_step": next_experiment.experiment.id,
                    }
                )
            # P0-6: persist rejected/validation notes added to the trace above.
            self.repo.save_decision_trace(decision_trace)

        predictions = self._register_predictions(decision, beliefs, request)

        # Persist the evaluated decision.
        decision.current_recommendation = decision_result.recommended_option_id
        decision.confidence = decision_result.confidence
        decision.convergence_status = convergence.status
        decision.critical_uncertainty_ids = [c.belief_id for c in criticals]
        decision.status = "EVALUATED"
        decision.rationale = decision_result.rationale
        decision.updated_at = utcnow()
        decision.version += 1
        self.repo.save_decision(decision)
        self._emit(
            EventType.DECISION_EVALUATED,
            "decision",
            decision.id,
            {"status": decision_result.status},
        )

        # V-2: persist the decision ledger record (recommendation -> action -> outcome).
        decision_record = DecisionRecord(
            id="DR_" + uuid4().hex,
            decision_id=decision.id,
            project_id=decision.project_id,
            recommendation=decision_result.recommended_option_id,
            model_version=request.model_tag,
            status="RECOMMENDED",
            abstain_reason=(
                "; ".join(decision_result.rationale[-1:])
                if decision_result.status == "ABSTAIN"
                else None
            ),
        )
        self.repo.save_decision_record(decision_record)
        self._emit(EventType.DECISION_RECORDED, "decision_record", decision_record.id, {})

        # P1-9: OpportunityCostEngine — AVAILABLE ENGINE / NOT ACTIVE BY
        # DEFAULT. Only when Settings.opportunity_cost_enabled is true and the
        # founder portfolio has an opportunity for this project do we write the
        # portfolio opportunity cost onto the decision options. Default False =
        # zero behavior change.
        if (
            self.settings.opportunity_cost_enabled
            and self.engines.opportunity_cost is not None
        ):
            portfolio = self.repo.get_portfolio(project.user_id)
            if portfolio is not None:
                opp = next(
                    (o for o in portfolio.opportunities if o.project_id == project.id),
                    None,
                )
                if opp is not None:
                    for option in decision.options:
                        option.opportunity_cost = round(opp.opportunity_cost, 4)
                    self.repo.save_decision(decision, expected_version=decision.version)
                    decision_trace.notes.append(
                        "opportunity_cost updated from portfolio (opt-in)"
                    )
                    self.repo.save_decision_trace(decision_trace)

        # Calibrated confidence (v1.1; UNCALIBRATED when insufficient samples).
        calibrated: CalibratedConfidence | None = None
        if self.engines.confidence_calibrator is not None:
            calibrated = self.engines.confidence_calibrator.calibrate(
                decision_result.confidence, "default"
            )

        rationale = (
            [
                f"Convergence: {convergence.status} — {convergence.reason}",
                f"Decision: {decision_result.status} (confidence={decision_result.confidence:.3f}).",
            ]
            + decision_result.rationale
        )
        belief_snapshot = [
            {
                "belief_id": b.id,
                "claim_id": b.claim_id,
                "probability": b.probability,
                "uncertainty": b.uncertainty,
                "posterior_version": b.posterior_version,
            }
            for b in sorted(beliefs, key=lambda x: x.id)
        ]
        evidence_used = sorted({e.id for e in all_applied})

        next_experiment_criteria: dict[str, str] = {}
        if next_experiment is not None:
            exp = next_experiment.experiment
            next_experiment_criteria = {
                "id": exp.id,
                "name": exp.name,
                "success_criteria": exp.success_criteria,
                "failure_criteria": exp.failure_criteria,
                "ambiguity_criteria": exp.ambiguity_criteria,
            }

        # V-7: presentation-layer action projection + advanced view. Both are
        # additive; Default callers simply see the new (optional) fields, and
        # ``advanced_view`` is stripped at the API layer unless ``advanced=true``.
        action_state = map_decision_type_to_action_state(
            decision_result.status,
            abstain_reason=(
                decision_result.rationale[-1]
                if decision_result.status == "ABSTAIN"
                else None
            ),
            has_next_experiment=(next_experiment is not None),
        )
        advanced_view = SolveResultAdvancedView(
            belief_graph=[
                e.model_dump(mode="json") for e in self.repo.list_belief_edges(project.id)
            ],
            utility={s.option_id: s.adjusted_utility for s in decision_result.option_scores},
            sensitivity=sensitivity,
            trace=decision_trace,
            stakes=decision.stakes.model_dump(mode="json") if decision.stakes else None,
        )

        return SolveResultV11(
            decision=decision_result,
            decision_id=decision.id,
            convergence=convergence,
            critical_uncertainties=criticals,
            next_experiment=next_experiment,
            predictions=predictions,
            rationale=rationale,
            confidence_calibrated=calibrated,
            why=decision_trace,
            belief_snapshot=belief_snapshot,
            what_could_change_my_mind=list(sensitivity.what_could_change_my_mind) if sensitivity else [],
            robustness=sensitivity.robustness if sensitivity else None,
            research_performed=traces,
            evidence_used=evidence_used,
            evidence_rejected=rejected_evidence,
            success_criteria=next_experiment_criteria.get("success_criteria") if next_experiment else None,
            failure_criteria=next_experiment_criteria.get("failure_criteria") if next_experiment else None,
            stop_condition=stop_report.status if stop_report else None,
            sensitivity=sensitivity,
            action_state=action_state,
            mode=request.mode,
            advanced_view=advanced_view,
            model_critique=model_critique,
        )

    # -- outcome closed loop -----------------------------------------------------

    def record_outcome(
        self,
        action_id: str,
        result: str,
        quantitative: dict[str, float] | None = None,
        outcome_type: OutcomeType | str = OutcomeType.PARTIAL,
        direction: str | None = None,
    ) -> OutcomeRecordedResult:
        """P2-16: delegated to OutcomeSettlementService (behavior identical)."""
        if self.engines.outcome_settlement_service is None:
            from vencertia.runtime.outcome_settlement_service import OutcomeSettlementService

            self.engines.outcome_settlement_service = OutcomeSettlementService(
                repo=self.repo,
                engines=self.engines,
                policy=self.policy,
                settings=self.settings,
                bus=self.bus,
            )
        return self.engines.outcome_settlement_service.record_outcome(
            action_id,
            result,
            quantitative=quantitative,
            outcome_type=outcome_type,
            direction=direction,
        )

    def evaluate_decision(self, decision_id: str) -> tuple[DecisionResult, ConvergenceReport]:
        decision = self.repo.get_decision(decision_id)
        if decision is None:
            raise EntityNotFoundError("decision", decision_id)
        beliefs = self.repo.get_beliefs(decision.project_id)
        criticals = self.engines.uncertainty_engine.rank(decision, beliefs)
        experiments = self.repo.list_experiments(decision.project_id)
        pre_convergence = self.engines.convergence_engine.check(
            decision, beliefs, criticals, experiments=experiments
        )
        result = self.engines.decision_engine.evaluate(
            DecisionEngineInput(
                decision=decision,
                beliefs=beliefs,
                risk_aversion=self.settings.risk_aversion,
                minimum_margin=self.settings.minimum_margin,
                max_critical_uncertainty=self.settings.max_critical_uncertainty,
                convergence_status=pre_convergence.status,
                convergence_reason=pre_convergence.reason,
            )
        )
        if result.status == "ABSTAIN":
            convergence = pre_convergence
        else:
            convergence = self.engines.convergence_engine.check(
                decision,
                beliefs,
                criticals,
                experiments=experiments,
                decision_status=result.status,
            )
        decision.current_recommendation = result.recommended_option_id
        decision.confidence = result.confidence
        decision.convergence_status = convergence.status
        decision.critical_uncertainty_ids = [c.belief_id for c in criticals]
        decision.status = "EVALUATED"
        decision.rationale = result.rationale
        decision.updated_at = utcnow()
        decision.version += 1
        self.repo.save_decision(decision, expected_version=decision.version - 1)
        self._emit(
            EventType.DECISION_RE_EVALUATED,
            "decision",
            decision.id,
            {"status": result.status, "convergence": convergence.status},
        )
        return result, convergence

    # -- internals ---------------------------------------------------------------

    def _build_context(
        self,
        project: Project,
        request: SolveRequest,
        decision: Decision | None = None,
    ) -> ContextBundle:
        """Build the context projection for a solve request.

        P0-1: ``decision`` is optional. pre-compile callers pass None (a
        decision does not exist yet); post-compile callers MUST pass
        ``compiled.decision`` so decision-relevance ranking is decision-aware.
        P2-16: delegated to CompilationService.
        """
        if self.engines.compilation_service is not None:
            return self.engines.compilation_service.build_context(
                project, request, decision=decision
            )
        if self.engines.context_builder_v11 is not None:
            return self.engines.context_builder_v11.build_for_decision(
                project.id, user_id=request.user_id, limit=15, decision=decision
            )
        return self.engines.context_builder.build(project.id, request.user_id, limit=15)

    def _load_or_create_project(self, project_id: str, user_id: str | None) -> Project:
        project = self.repo.get_project(project_id)
        if project is not None:
            return project
        project = Project(
            id=project_id,
            user_id=user_id or "u_default",
            name=f"Project {project_id}",
            description="Auto-created by SolveOrchestrator.",
            status=ProjectStatus.EXPLORING,
            stage=Stage.S0_INITIALIZATION,
        )
        self.repo.save_project(project)
        self._emit(EventType.PROJECT_STATE_CHANGED, "project", project.id, {"created": True})
        return project

    def _compile(self, request: SolveRequest, project: Project, context: ContextBundle | None) -> CompiledDecision:
        """P2-16: delegated to CompilationService (compiler reference shared)."""
        if self.engines.compilation_service is not None:
            self.engines.compilation_service.compiler = self.compiler
            self.engines.compilation_service.model = self.model
            compiled = self.engines.compilation_service.compile(request, project, context)
            self.compiler = self.engines.compilation_service.compiler
            return compiled
        compiler = self.compiler
        if compiler is None:
            from vencertia.capabilities import DecisionCompiler as DC
            from vencertia.providers.mock import MockProvider

            model = self.model or MockProvider()
            compiler = DC(model=model, settings=self.settings, repo=self.repo)
            self.compiler = compiler
        return compiler.compile(
            request.problem_text,
            {
                "project_id": project.id,
                "user_id": project.user_id,
                "domain": request.domain,
                "model_tag": request.model_tag,
            },
            options=request.options,
            context=context,
        )

    def _persist_compiled(self, compiled, request: SolveRequest) -> None:
        """P2-16: delegated to CompilationService."""
        if self.engines.compilation_service is not None:
            self.engines.compilation_service.persist(compiled, request)
            return
        # Objective
        if self.repo.get_objective(compiled.objective.id) is None:
            self.repo.save_objective(compiled.objective)
        # Claims
        for claim in compiled.claims:
            if self.repo.get_claim(claim.id) is None:
                self.repo.add_claim(claim)
        # Beliefs (existing canonical state wins)
        existing = self.repo.get_beliefs(request.project_id)
        existing_by_claim = {b.claim_id: b for b in existing}
        for belief in compiled.beliefs:
            if belief.claim_id in existing_by_claim:
                continue
            belief.project_id = request.project_id
            self.repo.save_belief(belief)
        self._emit(EventType.DECISION_CREATED, "decision", compiled.decision.id, {})

    def _run_research_round(
        self,
        request: SolveRequest,
        project: Project,
        decision: Decision,
        plan: ResearchPlan,
        round_no: int,
    ) -> tuple[ResearchTrace, list[Evidence]]:
        """Execute one research round → (trace, candidate evidence)."""
        question = plan.questions[(round_no - 1) % len(plan.questions)]
        queries = question.search_queries or [question.question]
        start = utcnow()
        candidates: list[Evidence] = []
        queries_executed = 0
        results_retrieved = 0
        trace_notes: list[str] = []

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
                    # the failure, degrade gracefully (no candidates from this
                    # query → the stop rule will declare SEARCH_EXHAUSTED).
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
                    if ev.project_id is None:
                        ev.project_id = project.id  # P0-3: "为该项目收集的"
                candidates.extend(evidence_list)
                results_retrieved += len(evidence_list)

        if self.retrieval is not None:
            docs = self.retrieval.retrieve(request.problem_text, k=3)
            for doc in docs:
                candidates.append(self._doc_to_evidence(doc, project.id))
                results_retrieved += 1

        provider = getattr(self.search, "name", "search") if self.search else "retrieval"
        model = getattr(self.model, "name", "mock") if self.model else "mock"
        trace = ResearchTrace(
            id="RT_" + uuid4().hex,
            decision_id=decision.id,
            question_id=question.id,
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
        """Legacy shim — the canonical implementation lives in
        :mod:`vencertia.runtime.research_service` (P0-5 single pipeline)."""
        from vencertia.runtime.research_service import ResearchExecutionService

        return ResearchExecutionService._doc_to_evidence(doc, project_id)

    @staticmethod
    def _evidence_to_result(evidence: Evidence) -> dict:
        """Legacy shim — the canonical implementation lives in
        :mod:`vencertia.runtime.research_service` (P0-5 single pipeline)."""
        return _research_evidence_to_result(evidence)

    def _ingest_evidence(self, candidates: list[Evidence]) -> list[Evidence]:
        """Gate + persist candidate evidence (candidate → validation → persist).

        Kept for compatibility with the v1.0 QA contract; the v1.1 solve path
        uses the ClaimBindingEngine pipeline instead.
        """
        applied: list[Evidence] = []
        for evidence in candidates:
            grade = self.policy.grade(evidence)
            if grade.scope_gate == "REJECTED":
                continue
            graded = self.policy.apply_authority(evidence, self.settings.policy_version)
            self.repo.add_evidence(graded)
            self._emit(
                EventType.EVIDENCE_ADDED,
                "evidence",
                graded.id,
                {"scope_gate": grade.scope_gate, "authority": graded.authority_level},
            )
            applied.append(graded)
        return applied

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

    def _register_predictions(
        self,
        decision: Decision,
        beliefs: list[Belief],
        request: SolveRequest,
    ) -> list[PredictionEntry]:
        entries = self.engines.prediction_ledger.register(
            decision,
            beliefs,
            domain=request.domain,
            model_tag=request.model_tag,
            module_tag="decision",
        )
        for entry in entries:
            # Single write (fresh insert, no expected_version) — M0-4.
            self.repo.save_prediction(entry)
            self._emit(EventType.PREDICTION_CREATED, "prediction", entry.id, {})
        return entries

    @staticmethod
    def _synthesize_default_experiment(
        decision: Decision, critical_belief_id: str | None
    ) -> Experiment:
        """Legacy shim — the canonical implementation lives in
        :mod:`vencertia.runtime.experiment_optimizer` (P0-6 single validator)."""
        from vencertia.runtime.experiment_optimizer import synthesize_default_experiment

        return synthesize_default_experiment(decision, critical_belief_id)

    @staticmethod
    def _direction_from_outcome_type(outcome_type: OutcomeType | str) -> str:
        raw = outcome_type.value if hasattr(outcome_type, "value") else str(outcome_type)
        if raw == "SUCCESS":
            return Direction.SUPPORTS.value
        if raw == "FAILURE":
            return Direction.CONTRADICTS.value
        return Direction.NEUTRAL.value

    @staticmethod
    def _strength_from_outcome_type(outcome_type: OutcomeType | str) -> float:
        raw = outcome_type.value if hasattr(outcome_type, "value") else str(outcome_type)
        return {"SUCCESS": 0.9, "FAILURE": 0.9, "PARTIAL": 0.5, "AMBIGUOUS": 0.3, "NOISE": 0.3}.get(
            raw, 0.5
        )
