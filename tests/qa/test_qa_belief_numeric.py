"""QA adversarial tests — Requirement 3: Evidence updates Beliefs (Beta-Bernoulli).

Hand-computed posterior assertions (alpha/beta pseudo-counts) to prove the
numerical formula, not just direction of movement.
"""

from __future__ import annotations

from vencertia.domain import Belief, Direction, Evidence, Scope, Verification
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.evidence_policy import EvidencePolicy

MAX_PSEUDO = 3.0  # settings.max_pseudo_observations


def _belief(alpha: float = 1.0, beta: float = 1.0) -> Belief:
    return Belief(
        id="BLF_1", claim_id="CLM_1", statement="will pay", scope=Scope.PROJECT,
        project_id="PRJ_1", alpha=alpha, beta=beta, decision_relevant=True,
    )


def _ev(
    eid: str,
    direction: str,
    evidence_type: str = "REAL_PAYMENT",
    authority: str = "PROJECT_REALITY",
    verification: str = "VERIFIED",
    strength: float = 1.0,
    reliability: float = 1.0,
    directness: float = 1.0,
    group: str | None = None,
) -> Evidence:
    return Evidence(
        id=eid, claim_ids=["CLM_1"], scope=Scope.PROJECT, evidence_type=evidence_type,
        source="test", directness=directness, reliability=reliability, relevance=1.0,
        strength=strength, supports_or_contradicts=direction, independence_group=group,
        authority_level=authority, verification=verification,
    )


def _update(beliefs, evidence):
    engine = BeliefEngine()
    return engine.update(
        BeliefUpdateInput(
            beliefs=beliefs, evidence=evidence, policy=EvidencePolicy(),
            max_pseudo_observations=MAX_PSEUDO,
        )
    )


def test_beta_bernoulli_single_support_posterior() -> None:
    """Prior Beta(1,1)=0.5 + one REAL_PAYMENT SUPPORTS (weight 1.0) -> Beta(4,1)=0.8."""
    out = _update([_belief()], [_ev("E_1", "SUPPORTS")])
    b = out.beliefs[0]
    assert b.alpha == 4.0 and b.beta == 1.0
    assert abs(b.posterior - 0.8) < 1e-9
    assert abs(b.probability - 0.8) < 1e-9
    app = out.applications[0]
    assert abs(app.alpha_delta - 3.0) < 1e-9
    assert app.beta_delta == 0.0


def test_support_then_contradict_returns_to_prior() -> None:
    """SUPPORTS then CONTRADICTS (equal weight) returns posterior to 0.5."""
    out = _update(
        [_belief()],
        [_ev("E_SUP", "SUPPORTS"), _ev("E_CON", "CONTRADICTS")],
    )
    b = out.beliefs[0]
    assert b.alpha == 4.0 and b.beta == 4.0
    assert abs(b.posterior - 0.5) < 1e-9


def test_dedup_discount_numeric() -> None:
    """Three correlated SUPPORTS in one group: weights 1.0, 0.5, 1/3."""
    out = _update(
        [_belief()],
        [
            _ev("E_1", "SUPPORTS", group="batch"),
            _ev("E_2", "SUPPORTS", group="batch"),
            _ev("E_3", "SUPPORTS", group="batch"),
        ],
    )
    b = out.beliefs[0]
    # alpha_deltas: 3.0, 1.5, 1.0 -> alpha = 1 + 5.5 = 6.5, beta = 1
    assert abs(b.alpha - 6.5) < 1e-9
    assert abs(b.posterior - 6.5 / 7.5) < 1e-9


def test_llm_evidence_weight_is_limited() -> None:
    """LLM_INFERENCE (0.20) with everything else 1.0 must move belief by weight 0.20."""
    out = _update(
        [_belief()],
        [_ev("E_LLM", "SUPPORTS", evidence_type="LLM_INFERENCE", authority="LLM_INFERENCE",
             verification="UNKNOWN")],
    )
    b = out.beliefs[0]
    # weight = 0.20 * 0.20(UNKNOWN multiplier) = 0.04; mass = 3 * 0.04 = 0.12
    assert abs(b.alpha - 1.12) < 1e-9
    assert abs(b.posterior - 1.12 / 2.12) < 1e-9


def test_prior_field_is_preserved_as_original() -> None:
    """Belief.prior records the pre-update posterior; evidence never rewrites it."""
    out = _update([_belief()], [_ev("E_1", "SUPPORTS")])
    b = out.beliefs[0]
    assert b.prior == 0.5  # original prior preserved
    assert b.posterior == 0.8
