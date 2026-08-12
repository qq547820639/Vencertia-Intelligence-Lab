"""L1Runner — historical time-sliced replay with leakage audit.

Each case carries only T0 information plus a future outcome. The harness never
injects hindsight into the decision; cases whose ``leakage_audit_passed`` is
not true are rejected outright (ADR-006).

Documented boundary (MINOR-L1-004): the leakage gate is a **flag-based,
authoring-time audit** — the flag is set by the case author/reviewer after a
manual audit. It is NOT a runtime content scan: a case whose flag is true but
whose T0 envelope accidentally contains future-looking data will run. This is
the documented contract (audit happens at case-authoring time), not a runtime
guard.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from vencertia.benchmark.harness import BenchmarkCaseResult, BenchmarkReport
from vencertia.benchmark.metrics import compute_all
from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Decision,
    Evidence,
    Experiment,
    VencertiaBaseModel,
)
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.convergence_engine import ConvergenceEngine
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput
from vencertia.runtime.evidence_policy import EvidencePolicy
from vencertia.runtime.experiment_optimizer import ExperimentOptimizer, ExperimentProposalInput
from vencertia.runtime.uncertainty_engine import UncertaintyEngine


class L1Case(VencertiaBaseModel):
    """A time-sliced historical case (canonical L1 contract, GAP-05).

    Canonical contract: this model, ``schemas/historical_decision_case.schema.json``,
    ``data/templates/historical_case_template.json`` and
    ``data/benchmarks/l1_cases.jsonl`` agree field-for-field.

    Backward compatibility: old cases that omit the T0 three fields
    (``claims_at_t0`` / ``beliefs_at_t0`` / ``evidence_at_t0``) default to ``[]``.
    They are NEVER backfilled from ``future_outcome`` / ``hindsight_data`` —
    that would be leakage (ADR-006).
    """

    id: str
    domain: str = "general"
    decision_time: datetime
    information_available_at_t0: dict[str, Any]  # full envelope (decision/beliefs/evidence/experiments)
    # Canonical T0 slices (v1.1+). Default [] for backward compatibility.
    claims_at_t0: list[dict[str, Any]] = Field(default_factory=list)
    beliefs_at_t0: list[dict[str, Any]] = Field(default_factory=list)
    evidence_at_t0: list[dict[str, Any]] = Field(default_factory=list)
    # Convenience mirrors of the envelope (populated from information_available_at_t0).
    decision: dict[str, Any] | None = None
    options: list[dict[str, Any]] | None = None
    # Gold reference: canonical names plus existing-naming compatibility.
    gold_decision: str | None = None
    actual_decision: str | None = None
    reference_option_id: str | None = None
    reference_experiment_id: str | None = None
    reference_critical_belief_id: str | None = None
    reference_convergence: str | None = None
    future_outcome: str | None = None
    hindsight_data: dict[str, Any] = Field(default_factory=dict)
    leakage_audit_passed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    reviewer_ids: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_gold_naming(cls, data: Any) -> Any:
        """Map canonical ``gold_decision`` onto existing ``reference_option_id``."""
        if not isinstance(data, dict):
            return data
        gold = data.get("gold_decision")
        existing = data.get("reference_option_id")
        if gold is not None and existing is not None and gold != existing:
            raise ValueError(
                f"gold_decision ({gold!r}) conflicts with reference_option_id ({existing!r})"
            )
        if gold is not None and existing is None:
            data["reference_option_id"] = gold
        return data

    @model_validator(mode="after")
    def _mirror_envelope(self) -> L1Case:
        """Expose decision/options mirrors from the T0 envelope when absent."""
        envelope = self.information_available_at_t0 or {}
        if self.decision is None and isinstance(envelope.get("decision"), dict):
            self.decision = envelope["decision"]
        if self.options is None:
            decision = self.decision or {}
            if isinstance(decision.get("options"), list):
                self.options = decision["options"]
        return self


class L1Runner:
    """Replays T0 snapshots through the deterministic engines."""

    def __init__(
        self,
        settings: Settings | None = None,
        policy: EvidencePolicy | None = None,
        belief_engine: BeliefEngine | None = None,
        uncertainty_engine: UncertaintyEngine | None = None,
        decision_engine: DecisionEngine | None = None,
        convergence_engine: ConvergenceEngine | None = None,
        experiment_optimizer: ExperimentOptimizer | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.policy = policy or EvidencePolicy(self.settings)
        self.belief_engine = belief_engine or BeliefEngine(self.settings, self.policy)
        self.uncertainty_engine = uncertainty_engine or UncertaintyEngine()
        self.decision_engine = decision_engine or DecisionEngine(
            self.settings, self.uncertainty_engine
        )
        self.convergence_engine = convergence_engine or ConvergenceEngine(self.settings)
        self.experiment_optimizer = experiment_optimizer or ExperimentOptimizer(self.settings)

    def run(self, path: str | Path) -> BenchmarkReport:
        path = Path(path)
        cases: list[L1Case] = []
        rejected: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if not raw.get("leakage_audit_passed", False):
                rejected.append(raw.get("id", "?"))
                continue
            cases.append(L1Case.model_validate(raw))

        results: list[BenchmarkCaseResult] = []
        passed = 0
        for case in cases:
            result = self._run_case(case)
            results.append(result)
            passed += 1 if result.correct else 0

        metrics = compute_all(
            [
                {
                    "predicted_option": r.predicted_option,
                    "gold_option": r.gold_option,
                    "decided": r.decided,
                    "correct": r.correct,
                    "predicted_experiment": r.predicted_experiment,
                    "gold_experiment": r.gold_experiment,
                    "predicted_critical": r.predicted_critical,
                    "gold_critical": r.gold_critical,
                    "chosen_utility": r.chosen_utility,
                    "best_utility": r.best_utility,
                }
                for r in results
            ]
        )
        # v1.1 metrics: L1 case files do not yet carry binding/efficiency gold
        # labels, so these are reported as None (rendered as N/A, never faked).
        metrics["claim_binding_accuracy"] = None
        metrics["research_efficiency"] = None
        metrics["evidence_yield"] = None
        metrics["belief_delta_quality"] = None
        metrics["decision_change_precision"] = None
        n = len(results)
        return BenchmarkReport(
            level="L1",
            source=str(path),
            n=n,
            passed=passed,
            failed=n - passed,
            pass_rate=round(passed / n, 6) if n else 0.0,
            metrics=metrics,
            cases=results,
            rejected=rejected,
        )

    def _run_case(self, case: L1Case) -> BenchmarkCaseResult:
        t0 = case.information_available_at_t0
        decision = Decision.model_validate(t0["decision"])
        beliefs = [Belief.model_validate(b) for b in t0.get("beliefs", [])]
        evidence = [Evidence.model_validate(e) for e in t0.get("evidence", [])]
        experiments = [Experiment.model_validate(e) for e in t0.get("experiments", [])]

        # Derive uncertainty/confidence from alpha/beta (derived state).
        for belief in beliefs:
            unc = self.belief_engine.uncertainty_of(belief)
            object.__setattr__(belief, "uncertainty", unc)
            object.__setattr__(belief, "confidence", max(0.0, min(1.0, 1.0 - unc)))

        if evidence:
            output = self.belief_engine.update(
                BeliefUpdateInput(
                    beliefs=beliefs,
                    evidence=evidence,
                    policy=self.policy,
                )
            )
            beliefs = output.beliefs

        criticals = self.uncertainty_engine.rank(decision, beliefs)
        pre_convergence = self.convergence_engine.check(
            decision, beliefs, criticals, experiments=experiments
        )
        result = self.decision_engine.evaluate(
            DecisionEngineInput(
                decision=decision,
                beliefs=beliefs,
                risk_aversion=self.settings.risk_aversion,
                minimum_margin=self.settings.minimum_margin,
                max_critical_uncertainty=self.settings.max_critical_uncertainty,
                convergence_status=pre_convergence.status,
            )
        )
        if result.status == "ABSTAIN":
            convergence = pre_convergence
        else:
            convergence = self.convergence_engine.check(
                decision,
                beliefs,
                criticals,
                experiments=experiments,
                decision_status=result.status,
            )
        predicted_option = result.recommended_option_id or "NO_DECISION"
        decided = result.status != "ABSTAIN"

        next_experiment_id: str | None = None
        if result.status == "ABSTAIN" and experiments:
            proposal = self.experiment_optimizer.propose(
                ExperimentProposalInput(
                    decision=decision,
                    beliefs=beliefs,
                    critical_belief_id=result.critical_belief_id,
                    candidates=experiments,
                )
            )
            if proposal.ranked:
                next_experiment_id = proposal.ranked[0].experiment.id

        checks: list[bool] = []
        if case.reference_option_id is not None:
            checks.append(predicted_option == case.reference_option_id)
        if case.reference_experiment_id is not None:
            checks.append(next_experiment_id == case.reference_experiment_id)
        if case.reference_critical_belief_id is not None:
            checks.append(result.critical_belief_id == case.reference_critical_belief_id)
        if case.reference_convergence is not None:
            checks.append(convergence.status == case.reference_convergence)
        correct = all(checks) if checks else True

        return BenchmarkCaseResult(
            id=case.id,
            predicted_option=predicted_option,
            gold_option=case.reference_option_id or "NO_DECISION",
            decided=decided,
            correct=correct,
            status=result.status,
            confidence=result.confidence,
            margin=result.decision_margin,
            predicted_experiment=next_experiment_id,
            gold_experiment=case.reference_experiment_id,
            experiment_correct=(
                next_experiment_id == case.reference_experiment_id
                if case.reference_experiment_id is not None
                else None
            ),
            predicted_critical=result.critical_belief_id,
            gold_critical=case.reference_critical_belief_id,
            critical_correct=(
                result.critical_belief_id == case.reference_critical_belief_id
                if case.reference_critical_belief_id is not None
                else None
            ),
            notes=case.notes,
        )
