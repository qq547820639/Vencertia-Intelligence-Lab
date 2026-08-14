"""L0Runner — synthetic strategy regression (26 + 10 capability cases).

Runs deterministic engines against gold-labeled cases (decision/abstention/
experiment/critical/convergence/probability references). Also normalizes and
runs the legacy v0.2.jsonl 24-case baseline to prove no behavioral regression.

v1.1 adds 10 capability cases (claim binding / unbound / multiple binding /
research stop / provider factory / context injection / dedup / contradiction /
sensitivity / calibration correction) dispatched via ``capability``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field

from vencertia.benchmark.harness import BenchmarkCaseResult, BenchmarkReport
from vencertia.benchmark.metrics import compute_all
from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    Claim,
    ClaimBindingInput,
    Decision,
    DecisionOption,
    DecisionResult,
    Evidence,
    Experiment,
    PredictionEntry,
    VencertiaBaseModel,
)
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.convergence_engine import ConvergenceEngine
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput
from vencertia.runtime.evidence_policy import EvidencePolicy
from vencertia.runtime.experiment_optimizer import ExperimentOptimizer, ExperimentProposalInput
from vencertia.runtime.uncertainty_engine import UncertaintyEngine


class L0Case(VencertiaBaseModel):
    """One synthetic regression case (decision-style or capability-style)."""

    id: str
    description: str = ""
    decision: Decision | None = None
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
    # v1.1 capability cases
    capability: str | None = None  # claim_binding | unbound | multiple_binding | ...
    params: dict = Field(default_factory=dict)
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
        decision_cases = [r for r in results if r.status]
        metrics = compute_all(
            [
                {
                    "predicted_option": r.predicted_option,
                    "gold_option": r.gold_option,
                    "predicted_status": r.status,
                    "gold_status": r.gold_status,
                    "decided": r.decided,
                    "correct": r.correct,
                    "predicted_experiment": r.predicted_experiment,
                    "gold_experiment": r.gold_experiment,
                    "predicted_critical": r.predicted_critical,
                    "gold_critical": r.gold_critical,
                    # L0 utilities are INTERNAL engine utilities (口径: engine
                    # adjusted utility), always present for decision cases.
                    "chosen_utility": r.chosen_utility,
                    "best_utility": r.best_utility,
                }
                for r in decision_cases
            ]
        )
        metrics["capability_passed"] = sum(
            1 for r in results if r.correct and not r.status
        )
        metrics["capability_total"] = sum(1 for r in results if not r.status)
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
        if case.capability:
            return self._run_capability_case(case)
        return self._run_decision_case(case)

    def _run_capability_case(self, case: L0Case) -> BenchmarkCaseResult:
        handler = getattr(self, f"_cap_{case.capability}", None)
        if handler is None:
            return BenchmarkCaseResult(
                id=case.id,
                predicted_option="NO_DECISION",
                gold_option="NO_DECISION",
                decided=False,
                correct=False,
                status="",
                notes=f"Unknown capability: {case.capability}",
            )
        try:
            ok, notes = handler(case)
        except Exception as exc:  # noqa: BLE001 - capability failures are recorded
            ok, notes = False, f"capability raised {type(exc).__name__}: {exc}"
        return BenchmarkCaseResult(
            id=case.id,
            predicted_option="CAPABILITY",
            gold_option="CAPABILITY",
            decided=False,
            correct=ok,
            status="",
            notes=notes,
        )

    # -- v1.1 capability handlers -------------------------------------------------

    def _cap_claim_binding(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.runtime.claim_binding import (
            ClaimBindingEngine,
            ClaimExtractor,
            DeterministicClaimMatcher,
            EvidenceClaimLinker,
        )

        params = case.params
        existing = Claim(
            id=params.get("claim_id", "CLM_X"),
            statement=params.get("existing_claim_statement", "ICP will pay for the outcome"),
            scope="PROJECT",
        )
        source = params.get("evidence_source", "Evidence that ICP will pay for the outcome")
        repo = _MemoryRepoProxy()
        engine = ClaimBindingEngine(
            extractor=ClaimExtractor(settings=self.settings),
            matcher=DeterministicClaimMatcher(self.settings),
            linker=EvidenceClaimLinker(),
            policy=self.policy,
            repo=repo,
            settings=self.settings,
        )
        output = engine.process(
            ClaimBindingInput(
                research_results=[{"id": "E_L0", "source": source, "scope": "MARKET"}],
                context={"claims": [existing]},
                existing_claims=[existing],
                binding_confidence_threshold=0.6,
            )
        )
        bound = len(output.bindings) > 0
        return bound, f"bindings={len(output.bindings)} unbound={len(output.unbound)}"

    def _cap_unbound(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.runtime.claim_binding import (
            ClaimBindingEngine,
            ClaimExtractor,
            DeterministicClaimMatcher,
            EvidenceClaimLinker,
        )

        params = case.params
        existing = Claim(
            id=params.get("claim_id", "CLM_X"),
            statement=params.get("existing_claim_statement", "ICP will pay for the outcome"),
            scope="PROJECT",
        )
        source = params.get(
            "evidence_source", "Unrelated market commentary about interest rates"
        )
        repo = _MemoryRepoProxy()
        engine = ClaimBindingEngine(
            extractor=ClaimExtractor(settings=self.settings),
            matcher=DeterministicClaimMatcher(self.settings),
            linker=EvidenceClaimLinker(),
            policy=self.policy,
            repo=repo,
            settings=self.settings,
        )
        output = engine.process(
            ClaimBindingInput(
                research_results=[{"id": "E_L0", "source": source, "scope": "MARKET"}],
                context={"claims": [existing]},
                existing_claims=[existing],
                binding_confidence_threshold=0.6,
            )
        )
        unbound_ok = len(output.unbound) > 0 and all(b.claim_id is None for b in output.unbound)
        return unbound_ok, f"bindings={len(output.bindings)} unbound={len(output.unbound)}"

    def _cap_multiple_binding(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.runtime.claim_binding import (
            ClaimBindingEngine,
            ClaimExtractor,
            DeterministicClaimMatcher,
            EvidenceClaimLinker,
        )

        params = case.params
        statements = params.get(
            "claim_statements", ["ICP has a severe recurring problem", "Problem severity drives churn"]
        )
        claims = [
            Claim(id=f"CLM_{i}", statement=s, scope="PROJECT") for i, s in enumerate(statements)
        ]
        source = params.get(
            "evidence_source", "ICP reports a severe recurring problem every week"
        )
        repo = _MemoryRepoProxy()
        engine = ClaimBindingEngine(
            extractor=ClaimExtractor(settings=self.settings),
            matcher=DeterministicClaimMatcher(self.settings),
            linker=EvidenceClaimLinker(),
            policy=self.policy,
            repo=repo,
            settings=self.settings,
        )
        output = engine.process(
            ClaimBindingInput(
                research_results=[{"id": "E_L0", "source": source, "scope": "MARKET"}],
                context={"claims": claims},
                existing_claims=claims,
                binding_confidence_threshold=0.5,
                binding_ambiguity_margin=params.get("binding_ambiguity_margin"),
            )
        )
        multi = len(output.bindings) >= 2
        return multi, f"bindings={len(output.bindings)} claims={sorted({b.claim_id for b in output.bindings})}"

    def _cap_research_stop(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.domain import ResearchTrace
        from vencertia.runtime.research_stop import ResearchStopRule

        params = case.params
        rule = ResearchStopRule(self.settings)
        delta = float(params.get("belief_delta", 0.001))
        dup_rate = float(params.get("duplicate_rate", 0.8))
        before = [Belief(id="b1", claim_id="CLM_1", statement="s", probability=0.5 - delta)]
        after = [Belief(id="b1", claim_id="CLM_1", statement="s", probability=0.5)]
        traces = [
            ResearchTrace(
                id="RT_L0", decision_id="DEC_L0", question_id="RQ_L0",
                results_retrieved=10, duplicate_dropped=int(dup_rate * 10), queries_executed=3,
                new_evidence_ids=[] if params.get("no_new_evidence") else ["E_1"],
            )
        ]
        report = rule.evaluate(
            traces, before, after, ["CLM_1"], round_no=2
        )
        expected = params.get("expected", "SEARCH_EXHAUSTED")
        return report.status == expected, f"status={report.status} signals={report.signals}"

    def _cap_provider_factory(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.providers.factory import create_provider_bundle

        params = case.params
        provider = params.get("model_provider", "mock")
        # v2.0.1: the benchmark case opts into mock EXPLICITLY (product default
        # is the real AI path and must not leak into benchmark machinery).
        cfg = Settings(model_provider=provider, search_provider="mock")
        bundle = create_provider_bundle(cfg)
        ok = getattr(bundle.model, "name", "") == "mock"
        ok = ok and (bundle.search is None or getattr(bundle.search, "name", "") == "mock_search")
        ok = ok and (
            bundle.retrieval is None or getattr(bundle.retrieval, "name", "") == "mock_retrieval"
        )
        return ok, (
            f"model={getattr(bundle.model, 'name', type(bundle.model).__name__)} "
            f"search={getattr(bundle.search, 'name', None) if bundle.search else None}"
        )

    def _cap_context_injection(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.runtime.context_ranker import ContextRanker

        ranker = ContextRanker(self.settings)
        decision = Decision(
            id="DEC_L0", decision_question="Should we build the MVP?", objective_id="OBJ_L0",
            project_id="PRJ_L0",
            options=[
                DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
                DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
            ],
            relevant_belief_ids=["wtp"],
        )
        beliefs = [Belief(id="wtp", claim_id="CLM_WTP", statement="wtp", probability=0.5)]
        strong_irrelevant = Evidence(
            id="E_IRR", claim_ids=[], scope="WORLD", evidence_type="REVIEWED_EXTERNAL_RESEARCH",
            source="Irrelevant global macro commentary", authority_level="REVIEWED_EXTERNAL_RESEARCH",
            strength=0.9, reliability=0.9, relevance=0.9,
        )
        medium_relevant = Evidence(
            id="E_REL", claim_ids=["CLM_WTP"], scope="PROJECT", evidence_type="OBSERVED_BEHAVIOR",
            source="ICP behavior about willingness to pay", authority_level="PROJECT_DIRECT_BEHAVIOR",
            strength=0.5, reliability=0.5, relevance=0.5,
        )
        score_rel = ranker.score_evidence(medium_relevant, decision, beliefs)
        score_irr = ranker.score_evidence(strong_irrelevant, decision, beliefs)
        return score_rel > score_irr, f"relevant={score_rel} irrelevant={score_irr}"

    def _cap_dedup(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.providers.search import content_fingerprint
        from vencertia.runtime.evidence_dedup import EvidenceDedupEngine

        params = case.params
        texts = params.get("texts", ["same text", "same text", "same text"])
        engine = EvidenceDedupEngine(self.settings)
        evidence_list = [
            Evidence(
                id=f"E_{i}", claim_ids=[], scope="MARKET", evidence_type="REVIEWED_EXTERNAL_RESEARCH",
                source=t, content_fingerprint=content_fingerprint(t),
            )
            for i, t in enumerate(texts)
        ]
        result = engine.group(evidence_list)
        expected_dropped = len(texts) - 1
        return len(result.dropped_ids) == expected_dropped, (
            f"dropped={len(result.dropped_ids)} kept={len(result.kept_ids)}"
        )

    def _cap_contradiction(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.runtime.conflict_engine import ConflictEngine

        support = Evidence(
            id="E_SUP", claim_ids=["CLM_X"], scope="PROJECT", evidence_type="OBSERVED_BEHAVIOR",
            source="supports", supports_or_contradicts="SUPPORTS", strength=0.9, reliability=0.9,
        )
        contradict = Evidence(
            id="E_CON", claim_ids=["CLM_X"], scope="PROJECT", evidence_type="OBSERVED_BEHAVIOR",
            source="contradicts", supports_or_contradicts="CONTRADICTS", strength=0.9, reliability=0.9,
        )
        engine = ConflictEngine(self.settings)
        conflicts = engine.detect({"CLM_X": [support, contradict]}, threshold=0.3)
        if not conflicts:
            return False, "no conflict detected"
        belief = Belief(id="b1", claim_id="CLM_X", statement="x", uncertainty=0.4)
        raised = engine.apply_to_belief(belief, conflicts[0])
        return conflicts[0].severity > 0 and raised.uncertainty > belief.uncertainty, (
            f"severity={conflicts[0].severity} unc={belief.uncertainty}->{raised.uncertainty}"
        )

    def _cap_sensitivity(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.runtime.decision_sensitivity import DecisionSensitivityEngine

        decision = Decision(
            id="DEC_L0", decision_question="q", objective_id="OBJ_L0", project_id="PRJ_L0",
            options=[
                DecisionOption(id="go", label="Go", kind="GO", base_utility=0.1,
                               belief_coefficients={"wtp": 0.8}, irreversible_cost=0.2),
                DecisionOption(id="hold", label="Hold", kind="HOLD", base_utility=0.35,
                               belief_coefficients={"wtp": 0.1}),
            ],
            relevant_belief_ids=["wtp"],
        )
        belief = Belief(
            id="wtp", claim_id="CLM_WTP", statement="wtp", probability=0.42, uncertainty=0.3,
        )
        from vencertia.runtime.uncertainty_engine import compute_option_scores

        scores = compute_option_scores(decision, [belief])
        result = DecisionResult(
            decision_id=decision.id, status="HOLD", recommended_option_id=scores[0].option_id,
            confidence=0.5, decision_margin=scores[0].adjusted_utility - scores[1].adjusted_utility,
            option_scores=scores,
        )
        engine = DecisionSensitivityEngine(self.settings)
        sensitivity = engine.compute(decision, [belief], result)
        ok = sensitivity.robustness in (
            "ROBUST_DECISION", "MODERATE_DECISION", "FRAGILE_DECISION"
        )
        return ok, (
            f"robustness={sensitivity.robustness} flips={[(f.direction, round(f.threshold_value, 2), f.would_become) for f in sensitivity.flips]}"
        )

    def _cap_calibration_correction(self, case: L0Case) -> tuple[bool, str]:
        from vencertia.repositories.memory import InMemoryRepository
        from vencertia.runtime.confidence_calibrator import ConfidenceCalibrator

        params = case.params
        repo = InMemoryRepository()
        samples = int(params.get("samples", 40))
        for i in range(samples):
            prob = 0.6 if i % 2 == 0 else 0.4
            repo.save_prediction(
                PredictionEntry(
                    id=f"PRD_L0_{i}", project_id="PRJ_L0", target="t",
                    predicted_probability=prob, resolution="TRUE" if prob > 0.5 else "FALSE",
                    outcome=prob > 0.5, domain="general",
                )
            )
        calibrator = ConfidenceCalibrator(repo=repo, settings=self.settings, min_samples=20)
        calibrated = calibrator.calibrate(0.55, "default")
        return calibrated.status == "CALIBRATED" and calibrated.calibrated is not None, (
            f"status={calibrated.status} calibrated={calibrated.calibrated} n={calibrated.n}"
        )

    def _run_decision_case(self, case: L0Case) -> BenchmarkCaseResult:
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

        assert case.decision is not None
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

        # A case with NO gold constraints cannot pass: treating it as correct
        # would silently inflate pass_rate (v1.9 honesty fix).
        correct = all(checks) if checks else False
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
            notes.append("No gold constraints; cannot pass (honest fail).")
        if case.company_case_isolation and not self._check_isolation(case):
            notes.append("Company-case isolation violated: project belief changed.")

        return BenchmarkCaseResult(
            id=case.id,
            predicted_option=predicted_option,
            gold_option=case.gold_option_id or "NO_DECISION",
            decided=decided,
            correct=correct,
            status=result.status,
            gold_status=case.gold_status,
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
    def _normalize_legacy_case(raw: dict[str, Any]) -> L0Case:
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


class _MemoryRepoProxy:
    """Minimal repository stand-in for capability handlers (in-memory only)."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def save_binding(self, binding, expected_version=None) -> None:
        self._data[f"binding:{binding.id}"] = binding

    def save_candidate_claim(self, candidate, expected_version=None) -> None:
        self._data[f"candidate:{candidate.id}"] = candidate

    def add_evidence(self, evidence) -> None:
        self._data[f"evidence:{evidence.id}"] = evidence

    def list_evidence(self, claim_ids=None):
        return [v for k, v in self._data.items() if k.startswith("evidence:")]
