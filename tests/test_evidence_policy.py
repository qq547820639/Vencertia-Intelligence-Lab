"""EvidencePolicy tests: authority hierarchy, LLM downgrade, company-case gate."""

from __future__ import annotations

from vencertia.domain import AuthorityLevel, Direction, Evidence, Scope, Verification


def _ev(evidence_type: str, scope: str = "PROJECT", **kw) -> Evidence:
    defaults = dict(
        id="E_" + evidence_type,
        claim_ids=["CLM_1"],
        scope=scope,
        evidence_type=evidence_type,
        source="test",
        directness=1.0,
        reliability=1.0,
        relevance=1.0,
        strength=1.0,
        supports_or_contradicts=Direction.SUPPORTS.value,
        authority_level="MODEL_PRIOR",
        verification="VERIFIED",
    )
    defaults.update(kw)
    return Evidence(**defaults)


def test_authority_hierarchy_has_nine_levels(policy):
    from vencertia.runtime.evidence_policy import AUTHORITY_TABLE

    assert len(AUTHORITY_TABLE) == 9
    assert policy.weight_of(AuthorityLevel.PROJECT_REALITY) == 1.00
    assert policy.weight_of(AuthorityLevel.MODEL_PRIOR) == 0.10


def test_evidence_type_maps_to_authority(policy):
    assert policy.grade(_ev("REAL_PAYMENT")).authority_level == AuthorityLevel.PROJECT_REALITY
    assert (
        policy.grade(_ev("CUSTOMER_COMMITMENT")).authority_level
        == AuthorityLevel.CUSTOMER_COMMITMENT_OR_PAYMENT
    )
    assert (
        policy.grade(_ev("LLM_INFERENCE")).authority_level == AuthorityLevel.LLM_INFERENCE
    )
    assert policy.grade(_ev("MODEL_PRIOR")).authority_level == AuthorityLevel.MODEL_PRIOR


def test_payment_beats_model_inference_weight(policy):
    pay = policy.grade(_ev("REAL_PAYMENT"))
    model = policy.grade(_ev("MODEL_PRIOR", verification="UNKNOWN"))
    assert pay.effective_weight > model.effective_weight


def test_llm_output_cannot_be_verified(policy):
    graded = policy.grade(_ev("LLM_INFERENCE", verification="VERIFIED"))
    # LLM output is downgraded: effective weight uses ESTIMATED multiplier.
    assert graded.effective_weight < policy.weight_of(AuthorityLevel.LLM_INFERENCE)


def test_company_case_without_transferability_is_gated(policy):
    evidence = _ev("COMPANY_CASE_FACT", scope="COMPANY_CASE", transferability=None)
    grade = policy.grade(evidence)
    assert grade.scope_gate == "COMPANY_CASE_PRIOR_ONLY"
    assert grade.authority_level == AuthorityLevel.MODEL_PRIOR


def test_company_case_with_transferability_becomes_eligible(policy):
    evidence = _ev(
        "COMPANY_CASE_FACT",
        scope="COMPANY_CASE",
        transferability=0.8,
    )
    grade = policy.grade(evidence)
    assert grade.scope_gate == "OK"
    assert grade.authority_level == AuthorityLevel.ELIGIBLE_EXTERNAL_CASE_FACT


def test_company_case_low_transferability_stays_gated(policy):
    evidence = _ev(
        "COMPANY_CASE_FACT", scope="COMPANY_CASE", transferability=0.3
    )
    grade = policy.grade(evidence)
    assert grade.scope_gate == "COMPANY_CASE_PRIOR_ONLY"


def test_apply_authority_writes_back(policy):
    evidence = _ev("REAL_PAYMENT")
    graded = policy.apply_authority(evidence, "1.0")
    assert graded.authority_level == AuthorityLevel.PROJECT_REALITY.value


def test_verification_multipliers(policy):
    assert policy.verification_multiplier("VERIFIED") == 1.0
    assert policy.verification_multiplier("ESTIMATED") == 0.75
    assert policy.verification_multiplier("ASSUMED") == 0.35
    assert policy.verification_multiplier("UNKNOWN") == 0.20


def test_version(policy):
    assert policy.version() == "1.0"
