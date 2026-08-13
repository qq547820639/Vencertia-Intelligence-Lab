"""OutcomeSettlementService — outcome closed loop (P2-16).

Extracted from SolveOrchestrator.record_outcome; behavior is field-for-field
identical to v1.1.1 (Outcome + Evidence + Belief updates + Prediction
settlement + Calibration + Decision re-evaluation + Action completion).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    CounterfactualStatus,
    DecisionOutcomeRecord,
    DecisionResult,
    Evidence,
    EvidenceType,
    Outcome,
    OutcomeType,
    PredictionEntry,
    Scope,
    utcnow,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import EventType, make_event
from vencertia.repositories.base import EntityNotFoundError, Repository
from vencertia.runtime.belief_engine import BeliefUpdateInput
from vencertia.runtime.decision_engine import DecisionEngineInput
from vencertia.runtime.evidence_policy import EvidencePolicy


class OutcomeSettlementService:
    """Record a real-world outcome and settle the closed loop."""

    def __init__(
        self,
        repo: Repository,
        engines,
        policy: EvidencePolicy,
        settings: Settings | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.repo = repo
        self.engines = engines
        self.policy = policy
        self.settings = settings or get_settings()
        self.bus = bus

    def record_outcome(
        self,
        action_id: str,
        result: str,
        quantitative: dict[str, float] | None = None,
        outcome_type: OutcomeType | str = OutcomeType.PARTIAL,
        direction: str | None = None,
    ) -> Any:
        """Record the outcome and settle the closed loop (P2-17 ATOMIC).

        The deterministic mutation batch — Outcome + Evidence + Belief updates
        + Prediction settlement + Calibration + Decision re-evaluation + Action
        completion — runs inside ``repo.in_transaction`` so a mid-batch failure
        rolls the WHOLE settlement back (no half batch).
        """
        holder: dict = {}

        def _batch() -> None:
            holder["result"] = self._record_outcome_impl(
                action_id, result, quantitative, outcome_type, direction
            )

        self.repo.in_transaction(_batch)
        return holder["result"]

    def _record_outcome_impl(
        self,
        action_id: str,
        result: str,
        quantitative: dict[str, float] | None = None,
        outcome_type: OutcomeType | str = OutcomeType.PARTIAL,
        direction: str | None = None,
    ) -> Any:
        """Record the outcome, generate evidence, update beliefs, settle
        predictions, update calibration and re-evaluate the decision."""
        from vencertia.domain import ConvergenceReport

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
            # P0-3: PROJECT evidence must be owned by the action's project.
            project_id=action.project_id,
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

        # V-2: backfill the decision ledger — regret is N/A without utility labels.
        if decision is not None:
            record = self.repo.get_decision_record(decision.id)
            if record is not None:
                record.action_taken = action.id
                record.status = "SETTLED"
                record.updated_at = utcnow()
                record.version += 1
                self.repo.save_decision_record(record, expected_version=record.version - 1)
                outcome_record = DecisionOutcomeRecord(
                    id="OLR_" + uuid4().hex,
                    decision_record_id=record.id,
                    outcome_id=outcome.id,
                    regret_estimate=None,
                    counterfactual_status=CounterfactualStatus.NOT_IDENTIFIABLE,
                )
                self.repo.save_decision_outcome_record(outcome_record)
                self._emit(
                    EventType.DECISION_OUTCOME_RECORDED,
                    "decision_outcome_record",
                    outcome_record.id,
                    {"decision_record_id": record.id},
                )

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
            decision_update, convergence = self._evaluate_decision(decision.id)
            action.status = "COMPLETED"
            action.completed_at = utcnow()
            action.version += 1
            self.repo.save_action(action, expected_version=action.version - 1)

        return self._result(
            outcome=outcome,
            graded=graded,
            updated_output=updated_output,
            decision_update=decision_update,
            convergence=convergence,
            calibration_delta=calibration_delta,
            resolved_predictions=resolved_predictions,
            action_id=action_id,
        )

    # -- helpers ---------------------------------------------------------------

    def _evaluate_decision(self, decision_id: str):
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

    def _result(
        self,
        outcome: Outcome,
        graded: Evidence,
        updated_output,
        decision_update,
        convergence,
        calibration_delta,
        resolved_predictions,
        action_id: str,
    ) -> Any:
        from vencertia.runtime.runtime import OutcomeRecordedResult

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

    def _save_belief_update_records(self, updated_output, conflicts=None) -> None:
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

    @staticmethod
    def _direction_from_outcome_type(outcome_type: OutcomeType | str) -> str:
        raw = outcome_type.value if hasattr(outcome_type, "value") else str(outcome_type)
        if raw == "SUCCESS":
            return "SUPPORTS"
        if raw == "FAILURE":
            return "CONTRADICTS"
        return "NEUTRAL"

    @staticmethod
    def _strength_from_outcome_type(outcome_type: OutcomeType | str) -> float:
        raw = outcome_type.value if hasattr(outcome_type, "value") else str(outcome_type)
        return {"SUCCESS": 0.9, "FAILURE": 0.9, "PARTIAL": 0.5, "AMBIGUOUS": 0.3, "NOISE": 0.3}.get(
            raw, 0.5
        )

    def _emit(self, event_type, entity_type: str, entity_id: str, payload=None) -> None:
        if self.bus is not None:
            self.bus.publish(make_event(event_type, entity_type, entity_id, payload))
