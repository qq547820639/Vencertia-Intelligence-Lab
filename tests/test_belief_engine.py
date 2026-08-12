"""BeliefEngine tests: Beta-Bernoulli updates, dedup, conflict, isolation."""

from __future__ import annotations

from vencertia.domain import (
    Belief,
    Evidence,
)
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput


def _belief(alpha=1.0, beta=1.0, scope="PROJECT") -> Belief:
    return Belief(
        id="BLF_1",
        claim_id="CLM_1",
        statement="will pay",
        scope=scope,
        project_id="PRJ_1",
        alpha=alpha,
        beta=beta,
        decision_relevant=True,
    )


def _ev(
    eid: str,
    direction: str,
    evidence_type: str = "REAL_PAYMENT",
    strength=1.0,
    reliability=1.0,
    directness=1.0,
    group=None,
    scope="PROJECT",
    authority="PROJECT_REALITY",
    verification="VERIFIED",
    transferability=None,
) -> Evidence:
    return Evidence(
        id=eid,
        claim_ids=["CLM_1"],
        scope=scope,
        evidence_type=evidence_type,
        source="test",
        directness=directness,
        reliability=reliability,
        relevance=1.0,
        strength=strength,
        supports_or_contradicts=direction,
        independence_group=group,
        authority_level=authority,
        verification=verification,
        transferability=transferability,
    )


def _update(beliefs, evidence, policy):
    engine = BeliefEngine(policy=policy)
    return engine.update(
        BeliefUpdateInput(beliefs=beliefs, evidence=evidence, policy=policy)
    )


def test_payment_moves_more_than_model_inference(policy):
    pay = _ev("E_PAY", "SUPPORTS", "REAL_PAYMENT")
    model = _ev("E_MOD", "SUPPORTS", "MODEL_PRIOR", authority="MODEL_PRIOR", verification="UNKNOWN")
    out = _update([_belief()], [pay, model], policy)
    app = {a.evidence_id: a for a in out.applications}
    assert app["E_PAY"].alpha_delta > app["E_MOD"].alpha_delta


def test_correlated_evidence_diminishes(policy):
    evidence = [
        _ev(f"E_{i}", "SUPPORTS", "PRIMARY_RESEARCH", group="batch", authority="REVIEWED_EXTERNAL_RESEARCH")
        for i in range(3)
    ]
    out = _update([_belief()], evidence, policy)
    weights = [a.effective_weight for a in sorted(out.applications, key=lambda a: a.evidence_id)]
    assert weights[0] > weights[1] > weights[2]


def test_neutral_evidence_adds_015_mass(policy):
    ev = _ev("E_NEU", "NEUTRAL", "FOUNDER_STATEMENT", authority="FOUNDER_STATEMENT")
    out = _update([_belief()], [ev], policy)
    app = out.applications[0]
    # mass = 3 * 0.45 = 1.35; each side 0.15*mass = 0.2025
    assert abs(app.alpha_delta - 0.2025) < 1e-9
    assert abs(app.beta_delta - 0.2025) < 1e-9
    assert out.beliefs[0].probability == 0.5  # balanced


def test_uncertainty_formula(policy):
    engine = BeliefEngine(policy=policy)
    b = Belief(
        id="BLF_U", claim_id="CLM_1", statement="x", scope="PROJECT", project_id="PRJ_1",
        posterior=0.8, probability=0.8, alpha=4.0, beta=1.0,
    )
    unc = engine.uncertainty_of(b)
    expected = 4 * 0.8 * 0.2 * (0.35 + 0.65 * (1 / (1 + 3 / 6)))
    assert abs(unc - expected) < 1e-9
    assert 0 <= unc <= 1


def test_conflict_detection(policy):
    sup = _ev("E_SUP", "SUPPORTS")
    con = _ev("E_CON", "CONTRADICTS")
    out = _update([_belief()], [sup, con], policy)
    assert len(out.conflicts) == 1
    assert out.conflicts[0].claim_id == "CLM_1"
    assert out.conflicts[0].weight_support >= policy.settings.conflict_weight_threshold
    assert out.conflicts[0].weight_contradict >= policy.settings.conflict_weight_threshold


def test_company_case_isolation_does_not_move_project_belief(policy):
    cc = _ev(
        "E_CC",
        "SUPPORTS",
        "COMPANY_CASE_FACT",
        scope="COMPANY_CASE",
        authority="MODEL_PRIOR",
        transferability=None,
    )
    b = _belief()  # scope PROJECT
    out = _update([b], [cc], policy)
    assert out.beliefs[0].probability == 0.5  # unchanged
    assert len(out.applications) == 0


def test_eligible_company_case_updates_prior_only(policy):
    cc = _ev(
        "E_CC_ELIG",
        "SUPPORTS",
        "ELIGIBLE_EXTERNAL_CASE_FACT",
        scope="COMPANY_CASE",
        authority="ELIGIBLE_EXTERNAL_CASE_FACT",
        transferability=0.8,
    )
    out = _update([_belief()], [cc], policy)
    app = out.applications[0]
    assert app.prior_only is True
    assert app.alpha_delta == 0.0 and app.beta_delta == 0.0
    assert out.beliefs[0].probability > 0.5  # small prior shift


def test_evidence_immutability(policy):
    ev = _ev("E_IMM", "SUPPORTS")
    original = ev.model_dump()
    _update([_belief()], [ev], policy)
    # Evidence object must not be mutated by the engine.
    assert ev.model_dump() == original


def test_belief_records_evidence_chain(policy):
    sup = _ev("E_CHAIN", "SUPPORTS")
    out = _update([_belief()], [sup], policy)
    b = out.beliefs[0]
    assert "E_CHAIN" in b.supporting_evidence_ids
    assert b.update_method == "BETA_BERNOULLI"
