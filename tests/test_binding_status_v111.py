"""BindingStatus four-state tests (GAP-01, v1.1.1).

Required scenarios:
  1. clear single                → BOUND
  2. clear multi                 → BOUND (multiple claims)
  3. no candidate                → UNBOUND_EVIDENCE
  4. two close candidates        → AMBIGUOUS (never force top-1)
  5. scope mismatch              → REJECTED
  6. company case → project dir  → REJECTED (company-case isolation)
  7. weak irrelevant             → UNBOUND_EVIDENCE (distinct from REJECTED)

Also covers the UNBOUND compat alias and the extended binding trace.
"""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import (
    BindingStatus,
    CandidateClaim,
    Claim,
    ClaimBindingInput,
    ClaimType,
    EvidenceClaimBinding,
    Scope,
)
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


def _engine(settings: Settings | None = None) -> ClaimBindingEngine:
    settings = settings or Settings()
    policy = EvidencePolicy(settings)
    return ClaimBindingEngine(
        extractor=ClaimExtractor(settings=settings),
        matcher=DeterministicClaimMatcher(settings),
        linker=EvidenceClaimLinker(),
        policy=policy,
        settings=settings,
    )


class _StubExtractor:
    """Deterministic extractor stub for crafted match-score scenarios."""

    def __init__(self, statements: list[tuple[str, float]]) -> None:
        self._statements = statements  # [(statement, extraction_confidence)]

    def extract(self, result: dict, context):
        candidates = []
        for idx, (statement, confidence) in enumerate(self._statements):
            candidates.append(
                CandidateClaim(
                    id=f"CC_STUB_{idx}",
                    statement=statement,
                    scope=Scope.MARKET,
                    claim_type=ClaimType.HYPOTHESIS,
                    extraction_confidence=confidence,
                )
            )
        return candidates


# ---------------------------------------------------------------------------
# 1. clear single → BOUND
# ---------------------------------------------------------------------------


def test_clear_single_binds_to_bound():
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_S1",
                    "source": "New data confirms ICP will pay for the promised outcome",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    assert len(output.bindings) == 1
    binding = output.bindings[0]
    assert binding.status == BindingStatus.BOUND
    assert binding.claim_id == "CLM_WTP"
    assert binding.selected_claim_ids == ["CLM_WTP"]
    assert binding.candidate_claim_ids == ["CLM_WTP"]
    assert binding.candidate_scores == {"CLM_WTP": 1.0}
    assert binding.reason == "clear match reached binding threshold"


# ---------------------------------------------------------------------------
# 2. clear multi → BOUND (multiple claims)
# ---------------------------------------------------------------------------


def test_clear_multi_binds_multiple_claims():
    """Two claims with a real score gap (margin=0) bind to both claims."""
    claim_a = Claim(
        id="CLM_A", statement="ICP has a severe recurring problem", scope=Scope.PROJECT
    )
    claim_b = Claim(
        id="CLM_B", statement="The recurring problem is severe for ICPs", scope=Scope.PROJECT
    )
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {"id": "E_S2", "source": "ICP has a severe recurring problem", "scope": "MARKET"}
            ],
            context={"claims": [claim_a, claim_b]},
            existing_claims=[claim_a, claim_b],
            auto_extract=True,
            binding_confidence_threshold=0.5,
            binding_ambiguity_margin=0.0,
        )
    )
    bound_ids = {b.claim_id for b in output.bindings}
    assert bound_ids == {"CLM_A", "CLM_B"}
    assert all(b.status == BindingStatus.BOUND for b in output.bindings)
    assert output.unbound == []


# ---------------------------------------------------------------------------
# 3. no candidate → UNBOUND_EVIDENCE
# ---------------------------------------------------------------------------


def test_no_candidate_is_unbound_evidence():
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_S3",
                    "source": "Completely unrelated global macro commentary",
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
    assert output.unbound[0].status == BindingStatus.UNBOUND_EVIDENCE
    assert output.unbound[0].claim_id is None
    assert output.unbound[0].candidate_claim_ids == []


# ---------------------------------------------------------------------------
# 4. two close candidates → AMBIGUOUS
# ---------------------------------------------------------------------------


def test_two_close_candidates_are_ambiguous():
    claim_a = Claim(
        id="CLM_A", statement="ICP has a severe recurring problem", scope=Scope.PROJECT
    )
    claim_b = Claim(
        id="CLM_B", statement="The recurring problem is severe for ICPs", scope=Scope.PROJECT
    )
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {"id": "E_S4", "source": "ICP has a severe recurring problem", "scope": "MARKET"}
            ],
            context={"claims": [claim_a, claim_b]},
            existing_claims=[claim_a, claim_b],
            auto_extract=True,
            binding_confidence_threshold=0.5,
        )
    )
    assert output.bindings == []
    assert len(output.unbound) == 1
    ambiguous = output.unbound[0]
    assert ambiguous.status == BindingStatus.AMBIGUOUS
    assert ambiguous.claim_id is None
    assert set(ambiguous.candidate_claim_ids) == {"CLM_A", "CLM_B"}
    assert ambiguous.selected_claim_ids == []
    assert "ambiguity margin" in ambiguous.reason


# ---------------------------------------------------------------------------
# 5. scope mismatch → REJECTED
# ---------------------------------------------------------------------------


def test_scope_mismatch_is_rejected():
    """COMPANY_CASE evidence with only a PROJECT claim → explicit REJECTED."""
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_S5",
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
    assert output.bindings == []
    assert len(output.unbound) == 1
    rejected = output.unbound[0]
    assert rejected.status == BindingStatus.REJECTED
    assert "scope mismatch" in rejected.reason


# ---------------------------------------------------------------------------
# 6. company case attempted project-direct → REJECTED
# ---------------------------------------------------------------------------


def test_company_case_attempted_project_direct_is_rejected():
    """COMPANY_CASE evidence cannot bind PROJECT claims (isolation rule)."""
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_S6",
                    "source": "ICP will pay for the promised outcome (company case fact)",
                    "scope": "COMPANY_CASE",
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
    rejected = output.unbound[0]
    assert rejected.status == BindingStatus.REJECTED
    assert "isolation" in rejected.reason or "scope mismatch" in rejected.reason


def test_company_case_may_bind_company_case_claim():
    """Same words, COMPANY_CASE claim → allowed by the scope matrix."""
    cc_claim = Claim(
        id="CLM_CC_WTP",
        statement="ICP will pay for the promised outcome",
        scope=Scope.COMPANY_CASE,
    )
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_S6B",
                    "source": "ICP will pay for the promised outcome (company case fact)",
                    "scope": "COMPANY_CASE",
                }
            ],
            context={"claims": [cc_claim]},
            existing_claims=[cc_claim],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    assert any(b.claim_id == "CLM_CC_WTP" for b in output.bindings)


# ---------------------------------------------------------------------------
# 7. weak irrelevant → UNBOUND_EVIDENCE (distinct from REJECTED)
# ---------------------------------------------------------------------------


def test_weak_irrelevant_is_unbound_not_rejected():
    """A candidate below binding_min_score is UNBOUND_EVIDENCE, not REJECTED."""
    settings = Settings(binding_min_score=0.7, binding_reject_threshold=0.4)
    engine = ClaimBindingEngine(
        extractor=_StubExtractor(
            [("ICPs will pay monthly for outcomes", 0.5)]
        ),
        matcher=DeterministicClaimMatcher(settings),
        linker=EvidenceClaimLinker(),
        policy=EvidencePolicy(settings),
        settings=settings,
    )
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {"id": "E_S7", "source": "unused", "scope": "MARKET"}
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
    assert unbound.status == BindingStatus.UNBOUND_EVIDENCE
    assert unbound.status != BindingStatus.REJECTED
    # The weak candidate was recorded in the trace but never bound.
    assert unbound.candidate_claim_ids == ["CLM_WTP"]
    assert 0.4 <= unbound.candidate_scores["CLM_WTP"] < 0.7


# ---------------------------------------------------------------------------
# UNBOUND compat alias + trace round-trip
# ---------------------------------------------------------------------------


def test_unbound_compat_alias_maps_to_unbound_evidence():
    assert BindingStatus.UNBOUND.value == "UNBOUND_EVIDENCE"
    assert BindingStatus.UNBOUND_EVIDENCE.value == "UNBOUND_EVIDENCE"
    # Persisted data with either name loads without breaking.
    binding = EvidenceClaimBinding(
        id="EB_ALIAS",
        evidence_id="E_ALIAS",
        claim_id=None,
        binding_confidence=0.0,
        status="UNBOUND_EVIDENCE",
    )
    assert binding.status == BindingStatus.UNBOUND_EVIDENCE
    assert binding.model_dump(mode="json")["status"] == "UNBOUND_EVIDENCE"


def test_binding_trace_fields_roundtrip():
    binding = EvidenceClaimBinding(
        id="EB_TRACE",
        evidence_id="E_TRACE",
        claim_id="CLM_WTP",
        binding_confidence=0.8,
        status=BindingStatus.BOUND,
        candidate_claim_ids=["CLM_WTP", "CLM_OTHER"],
        candidate_scores={"CLM_WTP": 0.9, "CLM_OTHER": 0.3},
        selected_claim_ids=["CLM_WTP"],
        reason="clear match reached binding threshold",
    )
    dumped = binding.model_dump(mode="json")
    restored = EvidenceClaimBinding.model_validate(dumped)
    assert restored.candidate_claim_ids == ["CLM_WTP", "CLM_OTHER"]
    assert restored.selected_claim_ids == ["CLM_WTP"]
    assert restored.reason == "clear match reached binding threshold"
    assert restored.status == BindingStatus.BOUND
