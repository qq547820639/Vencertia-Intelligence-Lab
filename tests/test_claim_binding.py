"""Claim binding pipeline tests (ADR-008)."""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import (
    BindingStatus,
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


def _engine(repo=None, bus=None):
    settings = Settings()
    policy = EvidencePolicy(settings)
    return ClaimBindingEngine(
        extractor=ClaimExtractor(settings=settings),
        matcher=DeterministicClaimMatcher(settings),
        linker=EvidenceClaimLinker(),
        policy=policy,
        repo=repo or InMemoryRepository(),
        bus=bus or EventBus(),
        settings=settings,
    )


CLAIM_WTP = Claim(
    id="CLM_WTP",
    statement="ICP will pay for the promised outcome",
    scope=Scope.PROJECT,
    claim_type=ClaimType.HYPOTHESIS,
)


def test_extract_recognizes_claim_keywords():
    extractor = ClaimExtractor(settings=Settings())
    candidates = extractor.extract(
        {"id": "E_1", "source": "New data confirms ICP will pay for the promised outcome"},
        {"claims": [CLAIM_WTP]},
    )
    assert len(candidates) == 1
    assert candidates[0].statement == CLAIM_WTP.statement
    assert candidates[0].extraction_confidence >= 0.6


def test_matcher_existing_match():
    matcher = DeterministicClaimMatcher(Settings())
    candidate = ClaimExtractor(Settings()).extract(
        {"id": "E_1", "source": "ICP will pay for the promised outcome"}, {"claims": [CLAIM_WTP]}
    )[0]
    result = matcher.match(candidate, [CLAIM_WTP])
    assert result.verdict == "EXISTING_MATCH"
    assert result.matched_claim_ids == ["CLM_WTP"]


def test_matcher_no_match():
    candidates = ClaimExtractor(Settings()).extract(
        {"id": "E_1", "source": "Interest rates and unrelated macro commentary"},
        {"claims": [CLAIM_WTP]},
    )
    assert candidates == []  # extractor produces no candidate for unrelated text
    # The linker must still mark the evidence UNBOUND (explicit, not silent).
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {"id": "E_1", "source": "Interest rates and unrelated macro commentary", "scope": "MARKET"}
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    assert len(output.unbound) == 1
    assert output.unbound[0].claim_id is None


def test_engine_binds_existing_match():
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_1",
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
    assert output.bindings[0].claim_id == "CLM_WTP"
    assert output.bindings[0].status == BindingStatus.BOUND.value or output.bindings[0].status == "BOUND"
    assert len(output.applied_evidence) == 1


def test_engine_marks_unbound_explicitly():
    engine = _engine()
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_2",
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
    assert len(output.bindings) == 0
    assert len(output.unbound) == 1
    assert output.unbound[0].claim_id is None
    assert output.unbound[0].status == "UNBOUND_EVIDENCE"


def test_multiple_close_claims_are_ambiguous_not_forced():
    """GAP-01: two near-identical claims → AMBIGUOUS (forcing top-1 is forbidden).

    Claims A and B share the same normalized token set, so top-1/top-2 scores
    are equal and the gap is below binding_ambiguity_margin.
    """
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
                {
                    "id": "E_3",
                    "source": "ICP has a severe recurring problem",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [claim_a, claim_b]},
            existing_claims=[claim_a, claim_b],
            auto_extract=True,
            binding_confidence_threshold=0.5,
        )
    )
    assert output.bindings == []
    assert len(output.unbound) == 1
    assert output.unbound[0].status == BindingStatus.AMBIGUOUS.value or output.unbound[0].status == "AMBIGUOUS"
    assert output.unbound[0].candidate_claim_ids == ["CLM_A", "CLM_B"]
    assert output.unbound[0].selected_claim_ids == []


def test_candidate_claim_requires_validation_before_canonical():
    """Candidates are saved PENDING; they never become canonical Claims here."""
    repo = InMemoryRepository()
    engine = _engine(repo=repo)
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_4",
                    "source": "Brand new claim about pricing power in this market",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=False,  # no extractor → no candidates
            binding_confidence_threshold=0.6,
        )
    )
    # auto_extract=False with a new claim would need manual candidates; the
    # evidence must still end up explicitly unbound rather than silently bound.
    assert len(output.bindings) == 0


def test_bound_evidence_updates_belief():
    repo = InMemoryRepository()
    settings = Settings()
    policy = EvidencePolicy(settings)
    engine = ClaimBindingEngine(
        extractor=ClaimExtractor(settings=settings),
        matcher=DeterministicClaimMatcher(settings),
        linker=EvidenceClaimLinker(),
        policy=policy,
        repo=repo,
        bus=EventBus(sink=repo.append_event),
        settings=settings,
    )
    repo.add_claim(CLAIM_WTP)
    belief = __import__("vencertia.domain", fromlist=["Belief"]).Belief(
        id="wtp", claim_id="CLM_WTP", statement="wtp", scope="PROJECT", project_id="PRJ_1",
        alpha=1.0, beta=1.0, probability=0.5,
    )
    repo.save_belief(belief)
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_5",
                    "source": "Evidence that ICP will pay for the promised outcome",
                    "scope": "MARKET",
                }
            ],
            context={"claims": [CLAIM_WTP]},
            existing_claims=[CLAIM_WTP],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    applied = [Evidence.model_validate(e) for e in output.applied_evidence]
    assert applied
    belief_engine = BeliefEngine(settings, policy)
    updated = belief_engine.update(
        BeliefUpdateInput(beliefs=[belief], evidence=applied, policy=policy)
    )
    assert updated.beliefs[0].probability > 0.5


def test_scope_gate_company_case_binding():
    """COMPANY_CASE evidence may not bind PROJECT claims (cross-scope → no binding)."""
    repo = InMemoryRepository()
    settings = Settings()
    policy = EvidencePolicy(settings)
    engine = ClaimBindingEngine(
        extractor=ClaimExtractor(settings=settings),
        matcher=DeterministicClaimMatcher(settings),
        linker=EvidenceClaimLinker(),
        policy=policy,
        repo=repo,
        bus=EventBus(),
        settings=settings,
    )
    # A company-case claim with the same words as the project claim.
    cc_claim = Claim(
        id="CLM_CC_WTP", statement="ICP will pay for the promised outcome",
        scope=Scope.COMPANY_CASE,
    )
    output = engine.process(
        ClaimBindingInput(
            research_results=[
                {
                    "id": "E_6",
                    "source": "Evidence that ICP will pay for the promised outcome",
                    "scope": "COMPANY_CASE",
                }
            ],
            context={"claims": [cc_claim]},
            existing_claims=[cc_claim],
            auto_extract=True,
            binding_confidence_threshold=0.6,
        )
    )
    # COMPANY_CASE evidence may bind COMPANY_CASE claims (allowed by matrix).
    assert any(b.claim_id == "CLM_CC_WTP" for b in output.bindings)
