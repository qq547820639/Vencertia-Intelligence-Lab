"""QA adversarial tests — Requirement 4: Company Case vs Project Evidence isolation.

The same company-case fact must behave differently before/after the
transferability threshold:
- transferability < 0.6 -> COMPANY_CASE_PRIOR_ONLY -> project WTP untouched.
- transferability >= 0.6 -> ELIGIBLE_EXTERNAL_CASE_FACT -> prior-only shift,
  NEVER pseudo-counts (alpha/beta unchanged).
"""

from __future__ import annotations

from vencertia.domain import Belief, Direction, Evidence, Scope, Verification
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.evidence_policy import EvidencePolicy


def _cc_evidence(eid: str, transferability: float | None) -> Evidence:
    return Evidence(
        id=eid, claim_ids=["CLM_X"], scope=Scope.COMPANY_CASE,
        evidence_type="COMPANY_CASE_FACT", source="case", directness=1.0,
        reliability=1.0, relevance=1.0, strength=1.0,
        supports_or_contradicts=Direction.SUPPORTS.value,
        authority_level="MODEL_PRIOR", verification=Verification.VERIFIED,
        transferability=transferability,
    )


def _belief(bid: str, scope: str, claim: str = "CLM_X") -> Belief:
    return Belief(
        id=bid, claim_id=claim, statement=bid, scope=scope, project_id="PRJ_1",
        alpha=1.0, beta=1.0, decision_relevant=True,
    )


def _update(beliefs, evidence):
    return BeliefEngine().update(
        BeliefUpdateInput(beliefs=beliefs, evidence=evidence, policy=EvidencePolicy())
    )


def test_low_transferability_never_touches_project_wtp() -> None:
    """transferability=0.3: project WTP posterior AND pseudo-counts unchanged."""
    out = _update(
        [_belief("BLF_PROJ", Scope.PROJECT.value)],
        [_cc_evidence("E_CC_LOW", 0.3)],
    )
    b = out.beliefs[0]
    assert b.probability == 0.5
    assert b.alpha == 1.0 and b.beta == 1.0
    # No application recorded against the project belief.
    assert all(a.belief_id != "BLF_PROJ" for a in out.applications)


def test_low_transferability_scope_gate_is_prior_only() -> None:
    grade = EvidencePolicy().grade(_cc_evidence("E_CC_LOW", 0.3))
    assert grade.scope_gate == "COMPANY_CASE_PRIOR_ONLY"
    assert grade.authority_level == "MODEL_PRIOR"


def test_eligible_transferability_moves_project_wtp_prior_only() -> None:
    """transferability=0.8: project WTP shifts by prior-only formula, counts intact.

    weight = 0.75 * 1.0 * 1.0 * 1.0 * 1.0 * 1.0 * 0.8 = 0.6
    delta  = 0.6 * (1 - 0.5) = 0.3 -> posterior 0.8; alpha/beta remain (1,1).
    """
    out = _update(
        [_belief("BLF_PROJ", Scope.PROJECT.value)],
        [_cc_evidence("E_CC_HIGH", 0.8)],
    )
    b = out.beliefs[0]
    assert abs(b.probability - 0.8) < 1e-9
    assert b.alpha == 1.0 and b.beta == 1.0  # NEVER pseudo-counts
    app = next(a for a in out.applications if a.belief_id == "BLF_PROJ")
    assert app.prior_only is True
    assert app.alpha_delta == 0.0 and app.beta_delta == 0.0


def test_company_case_never_adds_pseudo_counts_any_transferability() -> None:
    """For BOTH gated and eligible transferability, alpha+beta mass never grows."""
    for tr in (0.3, 0.8):
        out = _update(
            [_belief(f"BLF_{tr}", Scope.PROJECT.value)],
            [_cc_evidence(f"E_{tr}", tr)],
        )
        b = out.beliefs[0]
        assert b.alpha + b.beta == 2.0, f"pseudo-counts changed for transferability={tr}"


def test_gated_case_can_only_associate_world_market_company_case() -> None:
    """PRIOR_ONLY company case is blocked from PROJECT/CUSTOMER, allowed elsewhere.

    NOTE: the policy currently assigns effective_weight=0.0 for gated facts, so
    even WORLD/MARKET priors do NOT move (documented as 'may update' — see
    finding in QA report). This test pins the SAFE invariant: PROJECT never moves.
    """
    world = _belief("BLF_WORLD", Scope.WORLD.value)
    project = _belief("BLF_PROJ", Scope.PROJECT.value)
    customer = _belief("BLF_CUST", Scope.CUSTOMER.value)
    out = _update([world, project, customer], [_cc_evidence("E_GATED", 0.3)])
    by_id = {b.id: b for b in out.beliefs}
    assert by_id["BLF_PROJ"].probability == 0.5
    assert by_id["BLF_CUST"].probability == 0.5
