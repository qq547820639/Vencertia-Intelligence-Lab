"""QA adversarial tests — boundary conditions:
- 全冲突 CONFLICTED (strong support + strong contradict)
- SEARCH_EXHAUSTED -> EXPERIMENT_REQUIRED transition
- empty-evidence ABSTAIN identifies critical uncertainty
- decision engine requires >= 2 options
"""

from __future__ import annotations

import pytest

from vencertia.domain import (
    Belief,
    ConvergenceStatus,
    CriticalUncertainty,
    Decision,
    DecisionOption,
    Direction,
    Evidence,
    Experiment,
    Scope,
)
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.convergence_engine import ConvergenceEngine
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput
from vencertia.runtime.evidence_policy import EvidencePolicy


def _belief(bid: str, unc: float = 0.8) -> Belief:
    return Belief(
        id=bid, claim_id="CLM_" + bid, statement=bid, scope=Scope.PROJECT,
        project_id="PRJ_1", posterior=0.5, probability=0.5, alpha=1.0, beta=1.0,
        uncertainty=unc, decision_relevant=True,
    )


def _decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"],
    )


def _ev(eid: str, direction: str) -> Evidence:
    return Evidence(
        id=eid, claim_ids=["CLM_wtp"], scope=Scope.PROJECT, evidence_type="REAL_PAYMENT",
        source="x", directness=1.0, reliability=1.0, relevance=1.0, strength=1.0,
        supports_or_contradicts=direction, authority_level="PROJECT_REALITY",
        verification="VERIFIED",
    )


def test_full_conflict_detected() -> None:
    """Strong support + strong contradict -> CONFLICTED alert, posterior stays ~0.5."""
    out = BeliefEngine().update(
        BeliefUpdateInput(
            beliefs=[_belief("wtp")],
            evidence=[_ev("E_SUP", Direction.SUPPORTS.value), _ev("E_CON", Direction.CONTRADICTS.value)],
            policy=EvidencePolicy(),
        )
    )
    assert len(out.conflicts) == 1
    assert out.conflicts[0].claim_id == "CLM_wtp"
    assert abs(out.beliefs[0].probability - 0.5) < 1e-9  # balanced posterior


def test_empty_evidence_abstains_and_identifies_critical() -> None:
    """No evidence -> high uncertainty -> ABSTAIN + critical belief identified."""
    from vencertia.runtime.uncertainty_engine import UncertaintyEngine

    decision = Decision(
        id="DEC_2", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[
            DecisionOption(id="a", label="a", belief_coefficients={"wtp": 0.9}),
            DecisionOption(id="b", label="b", belief_coefficients={"wtp": -0.3}),
        ],
        relevant_belief_ids=["wtp"],
    )
    beliefs = [_belief("wtp", unc=1.0)]  # maximal uncertainty
    criticals = UncertaintyEngine().rank(decision, beliefs)
    assert criticals and criticals[0].belief_id == "wtp"
    result = DecisionEngine().evaluate(
        DecisionEngineInput(decision=decision, beliefs=beliefs, max_critical_uncertainty=0.45)
    )
    assert result.status == "ABSTAIN"
    assert result.critical_belief_id == "wtp"
    assert result.recommended_option_id is None


def test_search_exhausted_to_experiment_required_transition() -> None:
    """Same critical uncertainty: no experiments -> SEARCH_EXHAUSTED;
    an executable experiment exists -> EXPERIMENT_REQUIRED."""
    engine = ConvergenceEngine()
    decision = _decision()
    beliefs = [_belief("wtp", unc=0.9)]
    critical = [CriticalUncertainty(belief_id="wtp", statement="wtp", impact=0.8)]

    no_exp = engine.check(decision, beliefs, critical, experiments=[])
    assert no_exp.status == ConvergenceStatus.SEARCH_EXHAUSTED

    with_exp = engine.check(
        decision, beliefs, critical,
        experiments=[Experiment(id="EXP_1", name="pilot", target_belief_ids=["wtp"],
                                expected_information_gain=0.95, decision_impact=1.0,
                                cost=1.0, time=3.0)],
    )
    assert with_exp.status == ConvergenceStatus.EXPERIMENT_REQUIRED


def test_decision_requires_two_options() -> None:
    """A single-option decision cannot be evaluated."""
    decision = Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a")],
    )
    with pytest.raises(ValueError):
        DecisionEngine().evaluate(DecisionEngineInput(decision=decision, beliefs=[_belief("wtp")]))


def test_abstain_reports_experiment_proposal_contract() -> None:
    """ExperimentOptimizer.propose always reports decision_insufficient=True."""
    from vencertia.runtime.experiment_optimizer import (
        ExperimentOptimizer,
        ExperimentProposalInput,
    )

    proposal = ExperimentOptimizer().propose(
        ExperimentProposalInput(
            decision=_decision(), beliefs=[_belief("wtp", unc=1.0)],
            critical_belief_id="wtp", candidates=[],
        )
    )
    assert proposal.decision_insufficient is True
