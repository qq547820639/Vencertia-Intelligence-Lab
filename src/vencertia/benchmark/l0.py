"""L0Runner — synthetic strategy regression (24+ cases).

Runs deterministic engines against gold-labeled cases (decision/abstention/
experiment/critical/convergence/probability references). Also normalizes and
runs the legacy v0.2.jsonl 24-case baseline to prove no behavioral regression.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field

from vencertia.benchmark.harness import BenchmarkCaseResult, BenchmarkReport
from vencertia.benchmark.metrics import compute_all
from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Decision,
    DecisionOption,
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


class L0Case(VencertiaBaseModel):
    """One synthetic regression case."""

    id: str
    description: str = ""
    decision: Decision
    beliefs: list[Belief] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    gold_option_id: str | None = None
    gold_status: str | None = None  # GO/KILL/.../ABSTAIN
    gold_experiment_id: str | None = None
    gold_critical_belief_id: str | None = None
    gold_convergence: str | None = None
    expected_abstain: bool = False
    reference_probability: dict[str, float] | None = None
    company_case_isolation: bool = False
    # Optional per-case engine parameters (fall back to Settings defaults).
    risk_aversion: float | None = None
    minimum_margin: float | None = None
    max_critical_uncertainty: float | None = None


class L0Runner:
    """Deterministic L0 benchmark runner."""

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

    # -- public API ------------------------------------------------------------

    def run_cases(self, cases: list[L0Case]) -> BenchmarkReport:
        results: list[BenchmarkCaseResult] = []
        passed = 0
        for case in cases:
            case_result = self._run_case(case)
            results.append(case_result)
            passed += 1 if case_result.correct else 0
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
        n = len(results)
        return BenchmarkReport(
            level="L0",
            source="synthetic",
            n=n,
            passed=passed,
            failed=n - passed,
            pass_rate=round(passed / n, 6) if n else 0.0,
            metrics=metrics,
            cases=results,
        )

    def run_file(self, path: str | Path) -> BenchmarkReport:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cases = [L0Case.model_validate(c) for c in data.get("cases", [])]
        else:
            cases = [L0Case.model_validate(c) for c in data]
        return self.run_cases(cases)

    def run_legacy_file(self, path: str | Path) -> BenchmarkReport:
        """Normalize and run the v0.1/v0.2 jsonl legacy baseline."""
        path = Path(path)
        cases: list[L0Case] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            cases.append(self._normalize_legacy_case(raw))
        return self.run_cases(cases)

    # -- case execution ----------------------------------------------------------

    def _run_case(self, case: L0Case) -> BenchmarkCaseResult:
        # Beliefs are derived state: recompute uncertainty/confidence from
        # alpha/beta so authored cases behave identically to persisted ones.
        beliefs = {b.id: b.model_copy(deep=True) for b in case.beliefs}
        for belief in beliefs.values():
            unc = self.belief_engine.uncertainty_of(belief)
            object.__setattr__(belief, "uncertainty", unc)
            object.__setattr__(belief, "confidence", max(0.0, min(1.0, 1.0 - unc)))
        applied = case.evidence
        if applied:
            output = self.belief_engine.update(
                BeliefUpdateInput(
                    beliefs=list(beliefs.values()),
                    evidence=applied,
                    policy=self.policy,
                    max_pseudo_observations=self.settings.max_pseudo_observations,
                    conflict_weight_threshold=self.settings.conflict_weight_threshold,
                )
            )
            beliefs = {b.id: b for b in output.beliefs}

        belief_list = list(beliefs.values())
        criticals = self.uncertainty_engine.rank(case.decision, belief_list)
        pre_convergence = self.convergence_engine.check(
            case.decision, belief_list, criticals, experiments=case.experiments
        )
        result = self.decision_engine.evaluate(
            DecisionEngineInput(
                decision=case.decision,
                beliefs=belief_list,
                risk_aversion=case.risk_aversion or self.settings.risk_aversion,
                minimum_margin=case.minimum_margin or self.settings.minimum_margin,
                max_critical_uncertainty=(
                    case.max_critical_uncertainty or self.settings.max_critical_uncertainty
                ),
                convergence_status=pre_convergence.status,
            )
        )
        if result.status == "ABSTAIN":
            convergence = pre_convergence
        else:
            convergence = self.convergence_engine.check(
                case.decision,
                belief_list,
                criticals,
                experiments=case.experiments,
                decision_status=result.status,
            )

        predicted_option = result.recommended_option_id or "NO_DECISION"
        decided = result.status != "ABSTAIN"

        next_experiment_id: str | None = None
        if result.status == "ABSTAIN" and case.experiments:
            proposal = self.experiment_optimizer.propose(
                ExperimentProposalInput(
                    decision=case.decision,
                    beliefs=belief_list,
                    critical_belief_id=result.critical_belief_id,
                    candidates=case.experiments,
                )
            )
            if proposal.ranked:
                next_experiment_id = proposal.ranked[0].experiment.id

        # Gold comparison.
        checks: list[bool] = []
        if case.gold_option_id is not None:
            checks.append(predicted_option == case.gold_option_id)
        if case.gold_status is not None:
            checks.append(result.status == case.gold_status)
        if case.expected_abstain:
            checks.append(result.status == "ABSTAIN")
        if case.gold_experiment_id is not None:
            checks.append(next_experiment_id == case.gold_experiment_id)
        if case.gold_critical_belief_id is not None:
            checks.append(result.critical_belief_id == case.gold_critical_belief_id)
        if case.gold_convergence is not None:
            checks.append(convergence.status == case.gold_convergence)
        if case.reference_probability:
            for bid, expected in case.reference_probability.items():
                actual = beliefs[bid].probability if bid in beliefs else None
                checks.append(actual is not None and abs(actual - expected) < 1e-6)

        # Company-case isolation check: project belief must be unchanged.
        if case.company_case_isolation:
            checks.append(self._check_isolation(case))

        correct = all(checks) if checks else True
        chosen_utility = 0.0
        best_utility = 0.0
        for score in result.option_scores:
            chosen_utility = max(chosen_utility, score.adjusted_utility)
            best_utility = max(best_utility, score.adjusted_utility)
        if result.recommended_option_id is not None:
            for score in result.option_scores:
                if score.option_id == result.recommended_option_id:
                    chosen_utility = score.adjusted_utility

        notes = []
        if not checks:
            notes.append("No gold constraints; marked correct.")
        if case.company_case_isolation and not self._check_isolation(case):
            notes.append("Company-case isolation violated: project belief changed.")

        return BenchmarkCaseResult(
            id=case.id,
            predicted_option=predicted_option,
            gold_option=case.gold_option_id or "NO_DECISION",
            decided=decided,
            correct=correct,
            status=result.status,
            confidence=result.confidence,
            margin=result.decision_margin,
            predicted_experiment=next_experiment_id,
            gold_experiment=case.gold_experiment_id,
            experiment_correct=(
                next_experiment_id == case.gold_experiment_id
                if case.gold_experiment_id is not None
                else None
            ),
            predicted_critical=result.critical_belief_id,
            gold_critical=case.gold_critical_belief_id,
            critical_correct=(
                result.critical_belief_id == case.gold_critical_belief_id
                if case.gold_critical_belief_id is not None
                else None
            ),
            chosen_utility=chosen_utility,
            best_utility=best_utility,
            notes="; ".join(notes),
        )

    def _check_isolation(self, case: L0Case) -> bool:
        """Verify project beliefs are unchanged by COMPANY_CASE evidence."""
        base = {b.id: b.probability for b in case.beliefs}
        beliefs = {b.id: b.model_copy(deep=True) for b in case.beliefs}
        company_evidence = [e for e in case.evidence if e.scope == "COMPANY_CASE"]
        if company_evidence:
            output = self.belief_engine.update(
                BeliefUpdateInput(
                    beliefs=list(beliefs.values()),
                    evidence=company_evidence,
                    policy=self.policy,
                )
            )
            beliefs = {b.id: b for b in output.beliefs}
        project_beliefs = {b.id: b for b in beliefs.values() if b.scope == "PROJECT"}
        return all(
            abs(beliefs[bid].probability - base[bid]) < 1e-9
            for bid in project_beliefs
            if bid in base
        )

    # -- legacy normalization -----------------------------------------------------

    @staticmethod
    def _legacy_uncertainty(alpha: float, beta: float) -> float:
        """v0.1 uncertainty formula (variance x maturity), from alpha/beta."""
        p = alpha / (alpha + beta)
        variance = 4.0 * p * (1.0 - p)
        evidence_mass = alpha + beta - 2.0
        maturity = 1.0 / (1.0 + evidence_mass / 6.0)
        return max(0.0, min(1.0, variance * (0.35 + 0.65 * maturity)))

    @staticmethod
    def _normalize_legacy_case(raw: Dict[str, Any]) -> L0Case:
        request = raw["request"]
        beliefs: list[Belief] = []
        for b in request.get("beliefs", []):
            p = b["alpha"] / (b["alpha"] + b["beta"])
            unc = L0Runner._legacy_uncertainty(b["alpha"], b["beta"])
            beliefs.append(
                Belief(
                    id=b["id"],
                    claim_id="CLM_" + b["id"],
                    statement=b.get("statement", b["id"]),
                    project_id="PRJ_LEGACY",
                    posterior=p,
                    probability=p,
                    uncertainty=unc,
                    confidence=1.0 - unc,
                    alpha=b.get("alpha", 1.0),
                    beta=b.get("beta", 1.0),
                    decision_weight=b.get("decision_weight", 1.0),
                    decision_relevant=True,
                )
            )
        options: list[DecisionOption] = []
        for o in request.get("options", []):
            options.append(
                DecisionOption(
                    id=o["id"],
                    label=o.get("label", o["id"]),
                    description=o.get("description", ""),
                    kind=o.get("kind"),
                    base_utility=o.get("base_utility", 0.0),
                    belief_coefficients=o.get("belief_coefficients", {}),
                    irreversible_cost=o.get("irreversible_cost", 0.0),
                    opportunity_cost=o.get("opportunity_cost", 0.0),
                )
            )
        decision = Decision(
            id=request.get("id", raw.get("id", "legacy")),
            decision_question=request.get("question", ""),
            objective_id="OBJ_LEGACY",
            project_id="PRJ_LEGACY",
            options=options,
            horizon="short",
            reversible=True,
            relevant_belief_ids=[b["id"] for b in request.get("beliefs", [])],
            status="DRAFT",
        )
        experiments: list[Experiment] = []
        for e in raw.get("experiments", []):
            experiments.append(
                Experiment(
                    id=e["id"],
                    name=e.get("name", e["id"]),
                    target_belief_ids=e.get("target_belief_ids", []),
                    hypothesis=e.get("description", ""),
                    action=e.get("description", ""),
                    predicted_observation="",
                    success_criteria=e.get("success_signal", ""),
                    failure_criteria=e.get("failure_signal", ""),
                    ambiguity_criteria="",
                    expected_information_gain=e.get("expected_information_gain", 0.0),
                    decision_impact=e.get("decision_impact", 0.0),
                    cost=e.get("cost", 1.0),
                    time=e.get("days", e.get("time", 1.0)),
                    reversibility=e.get("reversibility", 1.0),
                )
            )
        evidence: list[Evidence] = []
        for e in request.get("evidence", []):
            from vencertia.legacy.mapping import authority_from_v10_2_source_type

            evidence.append(
                Evidence(
                    id=e.get("id", "E_LEGACY"),
                    claim_ids=["CLM_" + e.get("belief_id", "")],
                    scope="PROJECT",
                    evidence_type=e.get("evidence_type", "OBSERVED_BEHAVIOR"),
                    source=e.get("claim", ""),
                    directness=e.get("directness", 0.7),
                    reliability=e.get("source_reliability", 0.7),
                    relevance=1.0,
                    strength=e.get("strength", 0.8),
                    supports_or_contradicts=e.get("direction", "NEUTRAL"),
                    independence_group=e.get("independence_key"),
                    authority_level=authority_from_v10_2_source_type(
                        e.get("source_type")
                    ),
                    verification=e.get("verification", "UNKNOWN"),
                )
            )
        return L0Case(
            id=raw.get("id", "legacy"),
            description=raw.get("description", "legacy baseline"),
            decision=decision,
            beliefs=beliefs,
            evidence=evidence,
            experiments=experiments,
            gold_option_id=raw.get("gold_option_id"),
            gold_experiment_id=raw.get("gold_experiment_id"),
            gold_status=raw.get("gold_status"),
            gold_critical_belief_id=raw.get("gold_critical_belief_id"),
            gold_convergence=raw.get("gold_convergence"),
            expected_abstain=raw.get("expected_abstain", False),
            risk_aversion=request.get("risk_aversion"),
            minimum_margin=request.get("minimum_decision_margin"),
            max_critical_uncertainty=request.get("max_unresolved_critical_uncertainty"),
        )
