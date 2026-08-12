"""SolveOrchestrator — deterministic state-mutation entry point (ADR-002).

Flow: compile → load project/beliefs → research → evidence grade+add → belief
update → critical uncertainties → convergence → evaluate → (ABSTAIN → propose
experiment) → register predictions. And the outcome closed loop:
outcome → evidence → belief → decision re-evaluate → prediction settle →
calibration update.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import Field

from vencertia.capabilities import DecisionCompiler
from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Action,
    Belief,
    Claim,
    ConvergenceReport,
    CriticalUncertainty,
    Decision,
    DecisionOption,
    DecisionResult,
    Direction,
    Evidence,
    EvidenceType,
    Experiment,
    Objective,
    Outcome,
    OutcomeType,
    PredictionEntry,
    Project,
    ProjectStatus,
    RankedExperiment,
    Scope,
    Stage,
    VencertiaBaseModel,
    utcnow,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import DomainEvent, EventType, make_event
from vencertia.providers.models import ModelProvider, RetrievalProvider, SearchProvider
from vencertia.repositories.base import EntityNotFoundError, Repository
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.calibration_engine import CalibrationEngine, CalibrationInput
from vencertia.runtime.convergence_engine import ConvergenceEngine
from vencertia.runtime.context import ContextBuilder
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput
from vencertia.runtime.evidence_policy import EvidencePolicy
from vencertia.runtime.experiment_optimizer import (
    ExperimentOptimizer,
    ExperimentProposalInput,
)
from vencertia.runtime.opportunity_cost import OpportunityCostEngine
from vencertia.runtime.prediction_ledger import PredictionLedger
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


class OutcomeRecordedResult(VencertiaBaseModel):
    outcome: Outcome
    outcome_evidence: Evidence
    belief_deltas: list[Belief] = Field(default_factory=list)
    decision_update: DecisionResult | None = None
    convergence: ConvergenceReport | None = None
    calibration_delta: Optional[Dict[str, Any]] = None
    predictions_resolved: list[PredictionEntry] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


@dataclass
class EngineBundle:
    """All deterministic engines + ledger + context builder."""

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


def default_engine_bundle(
    repo: Repository,
    settings: Settings | None = None,
    bus: EventBus | None = None,
) -> EngineBundle:
    """Build a fully-wired EngineBundle for a repository."""
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
        payload: Dict[str, Any] | None = None,
    ) -> None:
        self.bus.publish(make_event(event_type, entity_type, entity_id, payload))

    # -- solve ----------------------------------------------------------------

    def solve(self, request: SolveRequest) -> SolveResult:
        project = self._load_or_create_project(request.project_id, request.user_id)
        compiled = self._compile(request, project)
        self._persist_compiled(compiled, request)

        # research candidates
        candidate_evidence = self._research(request, project)
        applied = self._ingest_evidence(candidate_evidence)

        beliefs = self.repo.get_beliefs(project.id)
        updated_output = self.engines.belief_engine.update(
            BeliefUpdateInput(
                beliefs=beliefs,
                evidence=applied,
                policy=self.policy,
                max_pseudo_observations=self.settings.max_pseudo_observations,
                conflict_weight_threshold=self.settings.conflict_weight_threshold,
            )
        )
        self._save_beliefs(updated_output.beliefs)

        decision = compiled.decision
        criticals = self.engines.uncertainty_engine.rank(decision, updated_output.beliefs)
        experiments = compiled.experiments or request.experiment_candidates
        pre_convergence = self.engines.convergence_engine.check(
            decision,
            updated_output.beliefs,
            criticals,
            experiments=experiments,
        )
        decision_result = self.engines.decision_engine.evaluate(
            DecisionEngineInput(
                decision=decision,
                beliefs=updated_output.beliefs,
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
                updated_output.beliefs,
                criticals,
                experiments=experiments,
                decision_status=decision_result.status,
            )

        next_experiment: RankedExperiment | None = None
        if decision_result.status == "ABSTAIN":
            proposal = self.engines.experiment_optimizer.propose(
                ExperimentProposalInput(
                    decision=decision,
                    beliefs=updated_output.beliefs,
                    critical_belief_id=decision_result.critical_belief_id,
                    candidates=experiments,
                    max_results=self.settings.experiment_max_results,
                )
            )
            if proposal.ranked:
                next_experiment = proposal.ranked[0]
            else:
                # Invariant (ADR-007): ABSTAIN must always carry a next
                # experiment, regardless of what the provider compiled. When no
                # candidate exists, synthesize a default one aimed at the
                # decision-critical belief.
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
            # Semantic consistency: once an executable experiment exists, the
            # convergence state cannot remain SEARCH_EXHAUSTED.
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

        predictions = self._register_predictions(decision, updated_output.beliefs, request)

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

        rationale = (
            [
                f"Convergence: {convergence.status} — {convergence.reason}",
                f"Decision: {decision_result.status} (confidence={decision_result.confidence:.3f}).",
            ]
            + decision_result.rationale
        )
        return SolveResult(
            decision=decision_result,
            decision_id=decision.id,
            convergence=convergence,
            critical_uncertainties=criticals,
            next_experiment=next_experiment,
            predictions=predictions,
            rationale=rationale,
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
        self._save_beliefs(updated_output.beliefs)
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
                            prediction.id, outcome.outcome_type == "SUCCESS"
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

    def _compile(self, request: SolveRequest, project: Project) -> "CompiledDecision":
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

    def _research(self, request: SolveRequest, project: Project) -> list[Evidence]:
        candidates: list[Evidence] = []
        if self.retrieval is not None:
            docs = self.retrieval.retrieve(request.problem_text, k=5)
            for doc in docs:
                candidates.append(
                    Evidence(
                        id=f"E_{uuid4().hex}",
                        claim_ids=[],
                        scope=Scope.MARKET,
                        evidence_type="REVIEWED_EXTERNAL_RESEARCH",
                        provenance={"tool": "RetrievalProvider", "source_id": doc.id},
                        source=doc.content,
                        directness=0.5,
                        reliability=0.6,
                        relevance=0.5,
                        strength=0.4,
                        supports_or_contradicts="SUPPORTS",
                        authority_level="REVIEWED_EXTERNAL_RESEARCH",
                        verification="ESTIMATED",
                    )
                )
        if self.search is not None:
            from vencertia.providers.search import SearchAdapter

            adapter = SearchAdapter(self.search)
            candidates.extend(
                adapter.to_candidate_evidence(request.problem_text, claim_ids=[], k=3)
            )
        return candidates

    def _ingest_evidence(self, candidates: list[Evidence]) -> list[Evidence]:
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

    def _save_beliefs(self, beliefs: list[Belief]) -> None:
        for belief in beliefs:
            existing = self.repo.get_belief(belief.id)
            expected = existing.version if existing is not None else None
            self.repo.save_belief(belief, expected_version=expected)
            self._emit(
                EventType.BELIEF_UPDATED,
                "belief",
                belief.id,
                {"probability": belief.probability, "uncertainty": belief.uncertainty},
            )

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
        from uuid import uuid4

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
