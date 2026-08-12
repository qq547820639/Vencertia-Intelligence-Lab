"""QA adversarial tests — Claim Binding closed loop (P0, ADR-008).

These tests deliberately go beyond the engineer's smoke tests: they assert
NUMERICAL belief deltas before/after binding, explicit UNBOUND handling,
many-to-many binding, and the deterministic candidate-validation gate that
prevents candidates from ever becoming canonical Claims silently.
"""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.domain import (
    Belief,
    BindingStatus,
    CandidateClaim,
    Claim,
    ClaimBindingInput,
    ClaimType,
    Evidence,
    Scope,
)
from vencertia.events.bus import EventBus
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.claim_binding import (
    ClaimBindingEngine,
    ClaimExtractor,
    DeterministicClaimMatcher,
    EvidenceClaimLinker,
)
from vencertia.runtime.evidence_policy import EvidencePolicy

CLAIM_WTP = Claim(
    id="CLM_WTP",
    statement="ICP will pay for the promised outcome",
    scope=Scope.PROJECT,
    claim_type=ClaimType.HYPOTHESIS,
)


def _engine(repo=None, bus=None, settings=None):
    settings = settings or Settings()
    policy = EvidencePolicy(settings)
    return (
        ClaimBindingEngine(
            extractor=ClaimExtractor(settings=settings),
            matcher=DeterministicClaimMatcher(settings),
            linker=EvidenceClaimLinker(),
            policy=policy,
            repo=repo or InMemoryRepository(),
            bus=bus or EventBus(),
            settings=settings,
        ),
        policy,
    )


def _belief(bid="wtp", claim_id="CLM_WTP", p=0.5):
    return Belief(
        id=bid, claim_id=claim_id, statement=claim_id, scope=Scope.PROJECT,
        project_id="PRJ_QA", probability=p, posterior=p, alpha=1.0, beta=1.0,
        uncertainty=0.5, decision_relevant=True,
    )


def test_qa_binding_closed_loop_belief_changes_numerically():
    """Search evidence bound to a claim MUST move the belief numerically."""
    repo = InMemoryRepository()
    settings = Settings()
    engine, policy = _engine(repo=repo)
    repo.add_claim(CLAIM_WTP)
    repo.save_belief(_belief(p=0.5))

    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_QA1",
                    "source": "Strong new evidence that ICP will pay for the promised outcome",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    # Bound, not unbound.
    assert len(output.bindings) == 1
    assert output.bindings[0].claim_id == "CLM_WTP"
    assert len(output.applied_evidence) == 1

    applied = [Evidence.model_validate(e) for e in output.applied_evidence]
    assert applied[0].claim_ids == ["CLM_WTP"]

    before = repo.get_belief("wtp")
    updated = BeliefEngine(settings, policy).update(
        BeliefUpdateInput(beliefs=[before], evidence=applied, policy=policy)
    )
    after = updated.beliefs[0]
    # Numeric assertion: supporting evidence must raise the probability.
    assert after.probability > before.probability
    assert after.probability - before.probability > 1e-6
    # posterior_version must increment.
    assert after.posterior_version > before.posterior_version
    assert before.posterior_version == 1
    assert after.posterior_version == before.posterior_version + 1
    # Update record captures old/new + discounts.
    assert len(updated.update_records) == 1
    rec = updated.update_records[0]
    assert rec.old_probability == pytest.approx(before.probability)
    assert rec.new_probability == pytest.approx(after.probability)
    assert rec.evidence_used == ["E_QA1"]
    assert rec.effective_weight > 0
    assert rec.freshness_discount == pytest.approx(1.0)
    assert rec.policy_version == "1.1"
    assert rec.posterior_version == after.posterior_version


def test_qa_unbound_evidence_is_explicit_and_not_silently_bound():
    """No match -> UNBOUND_EVIDENCE with claim_id=None; never silently attached."""
    repo = InMemoryRepository()
    engine, _ = _engine(repo=repo)
    repo.add_claim(CLAIM_WTP)

    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_QA2",
                    "source": "Macro interest-rate commentary totally unrelated to this venture",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    assert output.bindings == []
    assert len(output.unbound) == 1
    unbound = output.unbound[0]
    assert unbound.status == BindingStatus.UNBOUND_EVIDENCE.value or unbound.status == "UNBOUND_EVIDENCE"
    assert unbound.claim_id is None
    # Persisted as UNBOUND.
    persisted = repo.list_bindings(evidence_id="E_QA2")
    assert persisted and persisted[0].claim_id is None
    # The evidence itself must NOT carry a bound claim id (no silent binding).
    saved = repo.get_evidence("E_QA2")
    assert saved is not None
    assert saved.claim_ids == []
    # And no applied evidence was produced.
    assert output.applied_evidence == []


def test_qa_one_evidence_binds_multiple_claims():
    """GAP-01: an evidence may bind >=2 DISTINCT claims (gap >= ambiguity margin).

    The two claims share a strong token overlap but are not near-duplicates,
    so top-1/top-2 scores keep a gap >= binding_ambiguity_margin → BOUND
    to multiple claims (not AMBIGUOUS).
    """
    claim_a = Claim(id="CLM_A", statement="ICP has a severe recurring problem", scope=Scope.PROJECT)
    claim_b = Claim(id="CLM_B", statement="The recurring problem is severe for ICPs", scope=Scope.PROJECT)
    repo = InMemoryRepository()
    engine, _ = _engine(repo=repo)
    repo.add_claim(claim_a)
    repo.add_claim(claim_b)

    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_QA3",
                    "source": "ICP has a severe recurring problem",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [claim_a, claim_b]},
            existing_claims=[claim_a, claim_b],
            auto_extract=True,
            binding_confidence_threshold=0.5,
            binding_ambiguity_margin=0.0,  # GAP-01: zero margin ⇒ no ambiguity
        )
    )
    bound_ids = {b.claim_id for b in output.bindings}
    assert len(bound_ids) >= 2
    # Each binding is a separate persisted row.
    persisted = repo.list_bindings(evidence_id="E_QA3")
    assert len({b.claim_id for b in persisted}) >= 2


def test_qa_candidate_validation_gate_blocks_bad_candidates():
    """Candidates MUST pass deterministic validation; invalid ones are rejected."""
    engine, _ = _engine()

    bad_short = CandidateClaim(
        id="CC_BAD1", statement="ab", scope=Scope.PROJECT,
        claim_type=ClaimType.HYPOTHESIS, validation_status="PENDING",
    )
    assert engine._validate_candidate(bad_short, []) is False

    # model_construct bypasses pydantic enum validation so we can reach the
    # engine's defensive scope check (a real candidate could never carry an
    # invalid scope, but the gate must still guard the canonical boundary).
    bad_scope = CandidateClaim.model_construct(
        id="CC_BAD2", statement="a perfectly long statement", scope="NOT_A_SCOPE",
        claim_type=ClaimType.HYPOTHESIS, validation_status="PENDING",
        extraction_confidence=0.8,
    )
    assert engine._validate_candidate(bad_scope, []) is False

    good = CandidateClaim(
        id="CC_GOOD", statement="Founders can reach enough ICPs for validation",
        scope=Scope.PROJECT, claim_type=ClaimType.HYPOTHESIS,
        extraction_confidence=0.8, validation_status="PENDING",
    )
    assert engine._validate_candidate(good, []) is True
    # Duplicate of an existing claim (normalized equal) is rejected.
    dup = CandidateClaim(
        id="CC_DUP", statement="ICP will pay for the promised outcome",
        scope=Scope.PROJECT, claim_type=ClaimType.HYPOTHESIS,
        extraction_confidence=0.8, validation_status="PENDING",
    )
    assert engine._validate_candidate(dup, [CLAIM_WTP]) is False


def test_qa_new_candidate_saved_pending_never_canonical():
    """NO_MATCH candidate is saved PENDING and NEVER becomes a canonical Claim."""
    repo = InMemoryRepository()
    engine, _ = _engine(repo=repo)
    repo.add_claim(CLAIM_WTP)
    # Context has an additional claim the result text matches but that is NOT
    # among existing claims -> matcher returns NO_MATCH -> candidate saved PENDING.
    ctx_claim = Claim(
        id="CLM_NEW", statement="Founders can reach enough ICPs for validation",
        scope=Scope.PROJECT,
    )
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_QA4",
                    "source": "Founders can reach enough ICPs for validation, per our interviews",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [CLAIM_WTP, ctx_claim]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    assert len(output.new_candidates) == 1
    candidate = output.new_candidates[0]
    assert candidate.validation_status == "PENDING"
    # Saved as candidate.
    saved = repo.list_candidate_claims(validation_status="PENDING")
    assert any(c.id == candidate.id for c in saved)
    # NOT canonical: no Claim with that id exists in repo.
    assert repo.get_claim(candidate.id) is None
    assert repo.get_claim("CLM_NEW") is None
    # And since nothing was bound, evidence is explicitly UNBOUND (not silent).
    assert len(output.bindings) == 0
    assert len(output.unbound) >= 1


def test_qa_no_existing_claims_new_candidate_verdict_is_not_silently_bound():
    """KNOWN GAP (design intent): with zero existing claims the matcher returns
    NEW_CANDIDATE and the engine does not save it PENDING — it is dropped and
    the evidence is marked UNBOUND. This documents current behavior; the design
    (ADR-008) intends NEW_CANDIDATE to become a PENDING CandidateClaim."""
    repo = InMemoryRepository()
    engine, _ = _engine(repo=repo)
    ctx_claim = Claim(
        id="CLM_NEW2", statement="Founders can reach enough ICPs for validation",
        scope=Scope.PROJECT,
    )
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_QA4B",
                    "source": "Founders can reach enough ICPs for validation, per our interviews",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [ctx_claim]},
            existing_claims=[],  # no canonical claims yet
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    # Candidate NOT saved PENDING (gap), evidence explicitly UNBOUND (OK).
    assert output.new_candidates == []
    assert len(output.unbound) >= 1
    assert output.unbound[0].claim_id is None
    assert repo.list_candidate_claims() == []


def test_qa_scope_gate_company_case_cannot_bind_project_claim():
    """COMPANY_CASE evidence must NOT bind a PROJECT claim (scope matrix)."""
    repo = InMemoryRepository()
    engine, _ = _engine(repo=repo)
    repo.add_claim(CLAIM_WTP)  # PROJECT scope

    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_QA5",
                    "source": "A company case where ICP will pay for the promised outcome",
                    "scope": "COMPANY_CASE",
                }
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    # No binding to the PROJECT claim; the evidence is explicitly unbound.
    assert all(b.claim_id != "CLM_WTP" for b in output.bindings)
    assert len(output.unbound) >= 1


def test_qa_binding_confusion_matrix_precision():
    """Binding confidence = match_score x extraction_confidence; below threshold -> UNBOUND."""
    repo = InMemoryRepository()
    settings = Settings(binding_confidence_threshold=0.9)
    engine, _ = _engine(repo=repo, settings=settings)
    repo.add_claim(CLAIM_WTP)
    # Weak lexical match -> low extraction confidence -> below 0.9 threshold.
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_QA6",
                    "source": "Some firms will pay for a promised outcome in some cases",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.9,
        )
    )
    # Either not bound (confidence below threshold) or bound only if confidence
    # >= 0.9. Assert the invariant: no binding below the threshold.
    for b in output.bindings:
        assert b.binding_confidence >= 0.9
    if output.bindings:
        assert output.bindings[0].claim_id == "CLM_WTP"
    else:
        assert len(output.unbound) >= 1
