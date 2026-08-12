"""QA v1.1.1 Iteration 2 — adversarial edge cases for Claim Binding (GAP-01).

Targets (QA task list):
  1. binding ambiguity boundary: top1-top2 gap EXACTLY equal to margin
  2. rejected vs unbound semantic distinction (scope → REJECTED, no candidate → UNBOUND)
  3. old serialized binding status compat (literal "UNBOUND" alias read)
 12. score EXACTLY equal to binding_min_score (inclusive threshold)
 13. zero predicted / zero gold binding semantics

These tests use controlled stub extractor/matcher so the engine's four-state
classification logic is exercised precisely (no lexical-score guessing).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vencertia.config import Settings
from vencertia.domain import (
    BindingStatus,
    CandidateClaim,
    Claim,
    ClaimBindingInput,
    ClaimMatchResult,
    ClaimType,
    EvidenceClaimBinding,
    Scope,
)
from vencertia.runtime.claim_binding import (
    ClaimBindingEngine,
    DeterministicClaimMatcher,
    EvidenceClaimLinker,
)
from vencertia.runtime.evidence_policy import EvidencePolicy


def _settings(**kwargs) -> Settings:
    base = dict(
        binding_min_score=0.7,
        binding_ambiguity_margin=0.1,
        binding_reject_threshold=0.4,
        binding_confidence_threshold=0.6,
    )
    base.update(kwargs)
    return Settings(**base)


class _FixedExtractor:
    """Yields pre-built candidates with extraction_confidence=1.0."""

    def __init__(self, candidates: list[CandidateClaim]) -> None:
        self._candidates = candidates

    def extract(self, result: dict, context):
        return self._candidates


class _ControlledMatcher(DeterministicClaimMatcher):
    """Returns caller-specified scores per candidate id (deterministic).

    Inherits normalize() so the engine's candidate validation works.
    """

    def __init__(self, scores_by_candidate: dict[str, dict[str, float]]) -> None:
        super().__init__(_settings())
        self._scores = scores_by_candidate

    def match(self, candidate, existing, semantic=None):
        scores = self._scores.get(candidate.id, {})
        min_score = self.settings.binding_min_score
        matched = [(cid, s) for cid, s in scores.items() if s >= min_score]
        if not matched:
            return ClaimMatchResult(candidate=candidate, scores=scores, verdict="NO_MATCH")
        if len(matched) > 1:
            return ClaimMatchResult(
                candidate=candidate,
                matched_claim_ids=[cid for cid, _ in matched],
                scores=dict(matched),
                verdict="MULTIPLE_MATCH",
            )
        return ClaimMatchResult(
            candidate=candidate,
            matched_claim_ids=[matched[0][0]],
            scores=dict(matched),
            verdict="EXISTING_MATCH",
        )


def _candidate(cid: str, statement: str, scope: Scope = Scope.MARKET) -> CandidateClaim:
    return CandidateClaim(
        id=cid,
        statement=statement,
        scope=scope,
        claim_type=ClaimType.HYPOTHESIS,
        extraction_confidence=1.0,
    )


def _engine(settings: Settings, matcher) -> ClaimBindingEngine:
    return ClaimBindingEngine(
        extractor=_FixedExtractor([]),  # overridden below per-test
        matcher=matcher,
        linker=EvidenceClaimLinker(),
        policy=EvidencePolicy(settings),
        settings=settings,
    )


def _run(
    settings: Settings,
    candidates: list[CandidateClaim],
    scores: dict[str, dict[str, float]],
    claims: list[Claim],
    evidence_scope: str = "MARKET",
) -> tuple[ClaimBindingEngine, ClaimBindingInput, object]:
    engine = ClaimBindingEngine(
        extractor=_FixedExtractor(candidates),
        matcher=_ControlledMatcher(scores),
        linker=EvidenceClaimLinker(),
        policy=EvidencePolicy(settings),
        settings=settings,
    )
    inp = ClaimBindingInput(
        research_results=[{"id": "E_EDGE", "source": "s", "scope": evidence_scope}],
        context={"claims": claims},
        existing_claims=claims,
        auto_extract=True,
    )
    return engine, inp, engine.process(inp)


# ---------------------------------------------------------------------------
# 1. ambiguity boundary: top1-top2 gap exactly equal to margin
# ---------------------------------------------------------------------------


def test_gap_exactly_equal_to_margin_is_not_ambiguous():
    """Strict < semantics: gap == margin (0.10) → NOT ambiguous → BOUND.

    EXPECTED: with decimal-exact scores 0.90/0.80 and margin 0.10 the gap is
    exactly 0.10, which is NOT < 0.10, so the engine should bind both claims
    (clear multi, margin not violated).

    Fixed in MAJOR-CB-001: the top-1/top-2 gap is rounded to 7dp before the
    comparison, so 0.90-0.80 == 0.09999999999999998 → round(...,7) == 0.1 →
    BOUND (not misclassified AMBIGUOUS). Previously xfail(strict=True); the
    fix makes it a normal pass.
    """
    settings = _settings(binding_ambiguity_margin=0.1)
    claim_a = Claim(id="CLM_A", statement="A", scope=Scope.PROJECT)
    claim_b = Claim(id="CLM_B", statement="B", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "A"), _candidate("CC_2", "B")],
        scores={"CC_1": {"CLM_A": 0.90, "CLM_B": 0.80}},
        claims=[claim_a, claim_b],
    )
    assert {b.claim_id for b in out.bindings} == {"CLM_A", "CLM_B"}


def test_gap_below_margin_by_epsilon_is_ambiguous():
    """gap (0.0999999) < margin (0.10) → AMBIGUOUS (forcing top-1 forbidden)."""
    settings = _settings(binding_ambiguity_margin=0.1)
    claim_a = Claim(id="CLM_A", statement="A", scope=Scope.PROJECT)
    claim_b = Claim(id="CLM_B", statement="B", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "A"), _candidate("CC_2", "B")],
        scores={"CC_1": {"CLM_A": 0.90, "CLM_B": 0.8000001}},
        claims=[claim_a, claim_b],
    )
    assert out.bindings == []
    assert len(out.unbound) == 1
    assert out.unbound[0].status == BindingStatus.AMBIGUOUS
    assert set(out.unbound[0].candidate_claim_ids) == {"CLM_A", "CLM_B"}


def test_gap_above_margin_binds_all_reliable_claims():
    """gap (0.15) > margin (0.10) → clear multi: BOTH claims above confidence
    threshold bind (multi-claim BOUND, not top-1 forcing)."""
    settings = _settings(binding_ambiguity_margin=0.1)
    claim_a = Claim(id="CLM_A", statement="A", scope=Scope.PROJECT)
    claim_b = Claim(id="CLM_B", statement="B", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "A"), _candidate("CC_2", "B")],
        scores={"CC_1": {"CLM_A": 0.95, "CLM_B": 0.80}},
        claims=[claim_a, claim_b],
    )
    assert {b.claim_id for b in out.bindings} == {"CLM_A", "CLM_B"}


def test_zero_margin_allows_multi_bind():
    """margin=0.0: any score gap (no matter how small) is allowed → multi-BOUND."""
    settings = _settings(binding_ambiguity_margin=0.0)
    claim_a = Claim(id="CLM_A", statement="A", scope=Scope.PROJECT)
    claim_b = Claim(id="CLM_B", statement="B", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "A")],
        scores={"CC_1": {"CLM_A": 0.9, "CLM_B": 0.85}},
        claims=[claim_a, claim_b],
    )
    assert {b.claim_id for b in out.bindings} == {"CLM_A", "CLM_B"}


# ---------------------------------------------------------------------------
# 2. rejected vs unbound semantic distinction
# ---------------------------------------------------------------------------


def test_scope_violation_is_rejected_not_unbound():
    """COMPANY_CASE evidence with only a PROJECT claim → REJECTED."""
    settings = _settings()
    claim_p = Claim(id="CLM_P", statement="ICP will pay", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "ICP will pay")],
        scores={"CC_1": {"CLM_P": 1.0}},
        claims=[claim_p],
        evidence_scope="COMPANY_CASE",
    )
    assert out.bindings == []
    assert len(out.unbound) == 1
    assert out.unbound[0].status == BindingStatus.REJECTED
    assert "scope mismatch" in out.unbound[0].reason


def test_no_candidate_is_unbound_not_rejected():
    """No candidate at all → UNBOUND_EVIDENCE (never REJECTED)."""
    settings = _settings()
    claim_p = Claim(id="CLM_P", statement="ICP will pay", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[],  # extractor produced no candidates
        scores={},
        claims=[claim_p],
        evidence_scope="COMPANY_CASE",  # scope irrelevant when no candidate
    )
    assert out.bindings == []
    assert len(out.unbound) == 1
    assert out.unbound[0].status == BindingStatus.UNBOUND_EVIDENCE
    assert out.unbound[0].status != BindingStatus.REJECTED


def test_below_reject_threshold_is_unbound_not_rejected():
    """A candidate whose score is below reject_threshold is noise → UNBOUND,
    not REJECTED (REJECTED is reserved for rule violations on real candidates)."""
    settings = _settings()
    claim_p = Claim(id="CLM_P", statement="ICP will pay", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "unrelated")],
        scores={"CC_1": {"CLM_P": 0.2}},  # below reject_threshold 0.4
        claims=[claim_p],
    )
    assert out.bindings == []
    assert len(out.unbound) == 1
    assert out.unbound[0].status == BindingStatus.UNBOUND_EVIDENCE


# ---------------------------------------------------------------------------
# 12. score exactly equal to binding_min_score (inclusive threshold)
# ---------------------------------------------------------------------------


def test_score_exactly_equal_to_min_score_binds():
    """score == binding_min_score (0.7) is inclusive → BOUND when confidence ok."""
    settings = _settings(binding_min_score=0.7)
    claim_a = Claim(id="CLM_A", statement="A", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "A")],
        scores={"CC_1": {"CLM_A": 0.7}},
        claims=[claim_a],
    )
    assert {b.claim_id for b in out.bindings} == {"CLM_A"}


def test_score_below_min_score_by_epsilon_is_unbound():
    settings = _settings(binding_min_score=0.7)
    claim_a = Claim(id="CLM_A", statement="A", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "A")],
        scores={"CC_1": {"CLM_A": 0.6999999}},
        claims=[claim_a],
    )
    assert out.bindings == []
    assert out.unbound[0].status == BindingStatus.UNBOUND_EVIDENCE


def test_reject_threshold_exact_boundary_is_candidate():
    """score == reject_threshold (0.4) is included as a recorded candidate."""
    settings = _settings(binding_reject_threshold=0.4)
    claim_a = Claim(id="CLM_A", statement="A", scope=Scope.PROJECT)
    _, _, out = _run(
        settings,
        candidates=[_candidate("CC_1", "A")],
        scores={"CC_1": {"CLM_A": 0.4}},
        claims=[claim_a],
    )
    assert out.bindings == []
    assert len(out.unbound) == 1
    assert out.unbound[0].candidate_claim_ids == ["CLM_A"]
    assert out.unbound[0].status == BindingStatus.UNBOUND_EVIDENCE


# ---------------------------------------------------------------------------
# 3. old serialized binding status compat
# ---------------------------------------------------------------------------


def test_literal_unbound_string_is_rejected_by_pydantic():
    """Compat gap (MINOR): the enum NAME alias (BindingStatus.UNBOUND) exists,
    but pydantic validation does NOT accept the literal string 'UNBOUND'.
    Any legacy dataset that serialized the literal value 'UNBOUND' would fail
    to load. (Repo history always used 'UNBOUND_EVIDENCE', so no immediate
    breakage — but the docstring claim 'compatibility alias for persisted
    data' is overstated for the literal-value path.)"""
    with pytest.raises(ValidationError):
        EvidenceClaimBinding(
            id="EB_OLD",
            evidence_id="E_OLD",
            claim_id=None,
            binding_confidence=0.0,
            status="UNBOUND",
        )


def test_unbound_evidence_literal_still_loads():
    """The actual historical persisted value loads fine."""
    binding = EvidenceClaimBinding(
        id="EB_OK", evidence_id="E_OK", claim_id=None,
        binding_confidence=0.0, status="UNBOUND_EVIDENCE",
    )
    assert binding.status == BindingStatus.UNBOUND_EVIDENCE
    assert binding.status == BindingStatus.UNBOUND  # name alias equality


def test_unbound_name_alias_serializes_to_new_value():
    """Code using the old member NAME writes the canonical value."""
    binding = EvidenceClaimBinding(
        id="EB_ALIAS", evidence_id="E_ALIAS", claim_id=None,
        binding_confidence=0.0, status=BindingStatus.UNBOUND,
    )
    assert binding.model_dump(mode="json")["status"] == "UNBOUND_EVIDENCE"
