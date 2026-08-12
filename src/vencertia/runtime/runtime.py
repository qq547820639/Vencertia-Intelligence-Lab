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

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import Field

from vencertia.capabilities import CompiledDecision, DecisionCompiler
from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    CalibratedConfidence,
    ClaimBindingInput,
    ConvergenceReport,
    CriticalUncertainty,
    Decision,
    DecisionOption,
    DecisionResult,
    DecisionSensitivity,
    DecisionTrace,
    Direction,
    Evidence,
    EvidenceConflict,
    EvidenceType,
    Experiment,
    Outcome,
    OutcomeType,
    PredictionEntry,
    Project,
    ProjectStatus,
    RankedExperiment,
    ResearchPlan,
    ResearchStopReport,
    ResearchTrace,
    Scope,
    Stage,
    VencertiaBaseModel,
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


class SolveResult(VencertiaBaseModel):
    decision: DecisionResult
    decision_id: str
    convergence: ConvergenceReport
    critical_uncertainties: list[CriticalUncertainty] = Field(default_factory=list)
    next_experiment: RankedExperiment | None = None
    predictions: list[PredictionEntry] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


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
    return EngineBundle(
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

    # -- solve ----------------------------------------------------------------

    def solve(self, request: SolveRequest) -> SolveResult:
        project = self._load_or_create_project(request.project_id, request.user_id)
        pre_context = self._build_context(project, request)
        compiled = self._compile(request, project, pre_context)
        self._persist_compiled(compiled, request)
        decision = compiled.decision

        # Rebuild context after persisting compiled claims/beliefs so the
        # research pipeline sees real claims to bind against.
        context = self._build_context(project, request)

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
                trace, candidates = self._run_research_round(
                    request, project, decision, research_plan, round_no
                )
                traces.append(trace)

                kept = candidates
                if self.engines.dedup_engine is not None:
                    dedup = self.engines.dedup_engine.group(candidates)
                    trace.duplicate_dropped = len(dedup.dropped_ids)
                    kept_ids = set(dedup.kept_ids)
                    kept = [c for c in candidates if c.id in kept_ids]
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

                applied: list[Evidence] = []
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
                    applied = [Evidence.model_validate(e) for e in binding_output.applied_evidence]
                    rejected_evidence.extend(binding_output.rejected_evidence)
                    all_applied.extend(applied)
                    trace.new_evidence_ids = [e.id for e in applied]

                # ---- conflict + belief update ----------------------------------
                conflicts: list[EvidenceConflict] = []
                if applied and self.engines.conflict_engine is not None:
                    evidence_by_claim: dict[str, list[Evidence]] = {}
                    for evidence in all_applied:
                        for cid in evidence.claim_ids:
                            evidence_by_claim.setdefault(cid, []).append(evidence)
                    conflicts = self.engines.conflict_engine.detect(evidence_by_claim)
                    for conflict in conflicts:
                        self.repo.save_evidence_conflict(conflict)

                beliefs_for_update = self.repo.get_beliefs(project.id)
                if applied:
                    updated_output = self.engines.belief_engine.update(
                        BeliefUpdateInput(
                            beliefs=beliefs_for_update,
                            evidence=applied,
                            policy=self.policy,
                            max_pseudo_observations=self.settings.max_pseudo_observations,
                            conflict_weight_threshold=self.settings.conflict_weight_threshold,
                        )
                    )
                    # Apply conflict uncertainty raises.
                    raise_by_claim: dict[str, float] = {}
                    for conflict in conflicts:
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
                    self._save_beliefs(updated_output.beliefs, batch_id=trace.id)
                    self._save_belief_update_records(updated_output, conflicts)
                    beliefs = self.repo.get_beliefs(project.id)

                # ---- stop check ------------------------------------------------
                target_claims = [b.claim_id for b in beliefs]
                if self.engines.research_stop_rule is not None:
                    stop_report = self.engines.research_stop_rule.evaluate(
                        traces,
                        beliefs_before,
                        self.repo.get_beliefs(project.id) or beliefs,
                        target_claims,
                        decision=decision,
                        round_no=round_no,
                    )
                    trace.stop_status = stop_report.status
                    trace.stop_reason = stop_report.reason
                self.repo.save_research_trace(trace)
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
            if proposal.ranked:
                next_experiment = proposal.ranked[0]
            else:
                # Invariant (ADR-007): ABSTAIN must always carry a next
                # experiment, regardless of what the provider compiled.
                default = self._synthesize_default_experiment(
                    decision, decision_result.critical_belief_id
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
        action = self.repo.get_action(action_id)
        if action is None:
            raise EntityNotFoundError("action", action_id)

        decision = None
        if action.decision_id is not None:
            decision = self.repo.get_decision(action.decision_id)
        claim_ids: list[str] = []
        all_beliefs: list[Belief] = []
        if decision is not None:
            all_beliefs = self.repo.get_beliefs(decision.project_id)
            claim_ids = [b.claim_id for b in all_beliefs if b.id in decision.relevant_belief_ids]

        # Narrow to beliefs explicitly referenced in quantitative (e.g. {"wtp": 0.0}).
        belief_ids = {b.id for b in all_beliefs}
        hinted = [k for k in (quantitative or {}) if k in belief_ids]
        if hinted:
            claim_ids = [b.claim_id for b in all_beliefs if b.id in hinted]

        evidence_type = (
            EvidenceType.EXPERIMENT_RESULT.value
            if action.experiment_id
            else EvidenceType.OBSERVED_BEHAVIOR.value
        )
        authority = (
            "PROJECT_EXPERIMENT_RESULT" if action.experiment_id else "PROJECT_DIRECT_BEHAVIOR"
        )
        resolved_direction = direction or self._direction_from_outcome_type(outcome_type)
        strength = self._strength_from_outcome_type(outcome_type)

        evidence = Evidence(
            id=f"E_{uuid4().hex}",
            claim_ids=claim_ids,
            scope=Scope.PROJECT,
            evidence_type=evidence_type,
            provenance={"tool": "OutcomeService", "actor": "system", "raw_extract": result},
            source=result,
            directness=1.0,
            reliability=1.0,
            relevance=1.0,
            strength=strength,
            supports_or_contradicts=resolved_direction,
            observed_at=utcnow(),
            authority_level=authority,
            verification="VERIFIED",
        )
        graded = self.policy.apply_authority(evidence, self.settings.policy_version)

        outcome = Outcome(
            id=f"OUT_{uuid4().hex}",
            action_id=action_id,
            observed_at=utcnow(),
            result=result,
            quantitative=quantitative or {},
            outcome_type=outcome_type.value if hasattr(outcome_type, "value") else str(outcome_type),
            outcome_evidence_id=graded.id,
        )
        self.repo.save_outcome(outcome)
        self._emit(EventType.OUTCOME_RECORDED, "outcome", outcome.id, {"action_id": action_id})
        self.repo.add_evidence(graded)
        self._emit(EventType.EVIDENCE_ADDED, "evidence", graded.id, {"claim_ids": claim_ids})

        # Belief update on the decision's project.
        beliefs = self.repo.get_beliefs(decision.project_id if decision else action.project_id)
        updated_output = self.engines.belief_engine.update(
            BeliefUpdateInput(
                beliefs=beliefs,
                evidence=[graded],
                policy=self.policy,
                max_pseudo_observations=self.settings.max_pseudo_observations,
                conflict_weight_threshold=self.settings.conflict_weight_threshold,
            )
        )
        self._save_beliefs(updated_output.beliefs, batch_id=outcome.id)
        self._save_belief_update_records(updated_output, conflicts=[])
        for belief in updated_output.beliefs:
            self._emit(
                EventType.BELIEF_UPDATED,
                "belief",
                belief.id,
                {"probability": belief.probability, "uncertainty": belief.uncertainty},
            )

        # Resolve due predictions.
        resolved_predictions: list[PredictionEntry] = []
        if outcome.outcome_type in ("SUCCESS", "FAILURE"):
            open_predictions = self.repo.get_open_predictions(
                decision.project_id if decision else action.project_id
            )
            for prediction in open_predictions:
                if prediction.claim_id in claim_ids or not claim_ids:
                    try:
                        settled = self.engines.prediction_ledger.resolve(
                            prediction.id,
                            outcome.outcome_type == "SUCCESS",
                            resolution_source=outcome.id,
                        )
                    except ValueError:
                        continue
                    resolved_predictions.append(settled)
                    self._emit(
                        EventType.PREDICTION_RESOLVED,
                        "prediction",
                        settled.id,
                        {"resolution": settled.resolution, "outcome": settled.outcome},
                    )

        # Calibration update.
        calibration_delta = None
        try:
            profiles = self.engines.calibration_engine.update_all_scopes(
                self.repo.list_predictions(decision.project_id if decision else None)
            )
            if profiles:
                all_profile = next((p for p in profiles if p.scope == "ALL"), profiles[0])
                calibration_delta = all_profile.model_dump(mode="json")
        except Exception:  # pragma: no cover - calibration must not break outcome recording
            calibration_delta = None

        # Decision re-evaluate + convergence.
        decision_update: DecisionResult | None = None
        convergence: ConvergenceReport | None = None
        if decision is not None:
            decision_update, convergence = self.evaluate_decision(decision.id)
            action.status = "COMPLETED"
            action.completed_at = utcnow()
            action.version += 1
            self.repo.save_action(action, expected_version=action.version - 1)

        return OutcomeRecordedResult(
            outcome=outcome,
            outcome_evidence=graded,
            belief_deltas=updated_output.beliefs,
            decision_update=decision_update,
            convergence=convergence,
            calibration_delta=calibration_delta,
            predictions_resolved=resolved_predictions,
            rationale=[
                f"Recorded outcome {outcome.outcome_type} for action {action_id}.",
                f"Generated evidence {graded.id} with authority {graded.authority_level}.",
                f"Beliefs updated: {len(updated_output.beliefs)}; predictions resolved: {len(resolved_predictions)}.",
            ],
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

    def _build_context(self, project: Project, request: SolveRequest) -> ContextBundle:
        if self.engines.context_builder_v11 is not None:
            return self.engines.context_builder_v11.build_for_decision(
                project.id, user_id=request.user_id, limit=15
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

        if self.search is not None:
            from vencertia.providers.search import SearchAdapter

            adapter = SearchAdapter(self.search)
            for query in queries[: self.settings.research_queries_per_round]:
                queries_executed += 1
                evidence_list = adapter.to_candidate_evidence(
                    query, claim_ids=[], direction=Direction.SUPPORTS.value, k=2
                )
                candidates.extend(evidence_list)
                results_retrieved += len(evidence_list)

        if self.retrieval is not None:
            docs = self.retrieval.retrieve(request.problem_text, k=3)
            for doc in docs:
                candidates.append(self._doc_to_evidence(doc))
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
        )
        return trace, candidates

    @staticmethod
    def _doc_to_evidence(doc) -> Evidence:
        content = str(doc.content or "")
        lowered = content.lower()
        direction = Direction.SUPPORTS.value
        if "0 of" in lowered or "0/4" in lowered or "no " in lowered and "paid" in lowered:
            direction = Direction.CONTRADICTS.value
        source_text = content
        from vencertia.providers.search import canonical_source, content_fingerprint, source_family

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
        )

    @staticmethod
    def _evidence_to_result(evidence: Evidence) -> dict:
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
                evidence.verification.value if hasattr(evidence.verification, "value") else evidence.verification
            ),
            "content_fingerprint": evidence.content_fingerprint,
            "canonical_source_id": evidence.canonical_source_id,
            "source_family": evidence.source_family,
        }

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
        entries = self.engines.prediction_ledger.register(decision, beliefs)
        for entry in entries:
            entry.domain = request.domain
            entry.model_tag = request.model_tag
            entry.module_tag = "decision"
            self.repo.save_prediction(entry, expected_version=1)
            self._emit(EventType.PREDICTION_CREATED, "prediction", entry.id, {})
        return entries

    @staticmethod
    def _synthesize_default_experiment(
        decision: Decision, critical_belief_id: str | None
    ) -> Experiment:
        """Create a default decision-relevant experiment when the provider
        compiled no candidates (ADR-007: ABSTAIN must carry next_experiment)."""
        target = (
            [critical_belief_id]
            if critical_belief_id
            else list(decision.relevant_belief_ids)
        )
        target_label = critical_belief_id or ", ".join(decision.relevant_belief_ids) or "key assumption"
        return Experiment(
            id="EXP_" + uuid4().hex,
            decision_id=decision.id,
            name=f"Design and run a decision-relevant experiment for {target_label}",
            target_belief_ids=target,
            hypothesis=f"Resolve uncertainty about {target_label} enough to change the decision",
            action=f"Design and run the cheapest decisive experiment targeting {target_label}",
            predicted_observation="Outcome that materially updates the belief",
            success_criteria="Posterior uncertainty drops below the decision threshold",
            failure_criteria="No decision-relevant signal obtained",
            ambiguity_criteria="Ambiguous or mixed signal",
            expected_information_gain=0.6,
            decision_impact=0.9,
            cost=1.0,
            time=1.0,
            reversibility=1.0,
        )

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
