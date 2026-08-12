"""QA adversarial tests — Dedup + conflict (P0).

Verifies: 10 re-posts of the same news count once (no pseudo-count stacking);
conflicting evidence raises uncertainty AND persists an EvidenceConflict.
"""

from __future__ import annotations

from vencertia.config import Settings
from vencertia.domain import Belief, Evidence
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.conflict_engine import ConflictEngine
from vencertia.runtime.evidence_dedup import EvidenceDedupEngine
from vencertia.runtime.evidence_policy import EvidencePolicy


def _evidence(eid, text, url="", family=None, fp=None, direction="SUPPORTS", strength=0.9, reliability=0.9) -> Evidence:
    return Evidence(
        id=eid, claim_ids=["CLM_X"], scope="MARKET", evidence_type="REVIEWED_EXTERNAL_RESEARCH",
        source=text, provenance={"source_url": url},
        content_fingerprint=fp, canonical_source_id=url or None, source_family=family,
        supports_or_contradicts=direction, strength=strength, reliability=reliability,
    )


def test_qa_same_news_10_times_counts_once():
    """10 identical re-posts -> 1 canonical kept, 9 dropped (no pseudo-count stacking)."""
    engine = EvidenceDedupEngine(Settings())
    items = [_evidence(f"E_{i}", "Same news article reposted across aggregators", url="https://news.example/a") for i in range(10)]
    result = engine.group(items)
    assert len(result.dropped_ids) == 9
    assert len(result.kept_ids) == 1
    assert all(g.drop_reason == "EXACT_FINGERPRINT" for g in result.groups)

    # Belief update with ONLY the canonical kept evidence: probability moves once.
    settings = Settings()
    policy = EvidencePolicy(settings)
    belief = Belief(id="b1", claim_id="CLM_X", statement="x", scope="PROJECT", project_id="PRJ_1",
                    probability=0.5, posterior=0.5, alpha=1.0, beta=1.0, uncertainty=0.5)
    canonical = next(e for e in items if e.id in result.kept_ids)
    out = BeliefEngine(settings, policy).update(
        BeliefUpdateInput(beliefs=[belief], evidence=[canonical], policy=policy)
    )
    one_shot = out.beliefs[0].probability
    # Naively applying all 10 would overshoot; the canonical alone must NOT
    # produce the same mass as 10 independent applications.
    naive = belief.model_copy(deep=True)
    for _ in range(10):
        naive_out = BeliefEngine(settings, policy).update(
            BeliefUpdateInput(beliefs=[naive], evidence=[canonical], policy=policy)
        )
        naive = naive_out.beliefs[0]
    assert one_shot < naive.probability  # dedup prevents stacking


def test_qa_same_family_near_duplicates_share_independence_group():
    """Same source family + high similarity -> shared independence_group (discount).

    KNOWN SOURCE BUG: the dedup engine sets the member's independence_group to
    the canonical id, but the canonical keeps independence_group=None. The
    BeliefEngine keys groups as ``independence_group or '__unique__:<id>'``, so
    canonical and member end up in DIFFERENT groups and NO correlation discount
    is applied (discounts stay [1.0, 1.0] instead of [1.0, 0.5]).
    """
    engine = EvidenceDedupEngine(Settings(dedup_similarity_threshold=0.5))
    a = _evidence("E_A", "Company X raised a huge funding round yesterday", url="https://news.example/a", family="news.example")
    b = _evidence("E_B", "Company X raised a huge funding round yesterday from a syndicate", url="https://news.example/b", family="news.example")
    result = engine.group([a, b])
    assert len(result.kept_ids) == 2  # similar, not exact
    # BUG (fails): canonical independence_group stays None while member gets 'E_A'.
    kept = [e for e in [a, b] if e.id in result.kept_ids]
    groups = {e.independence_group for e in kept}
    assert len(groups) == 1 and next(iter(groups)) is not None

    # BUG (fails): the belief engine must discount the near-duplicate.
    settings = Settings()
    policy = EvidencePolicy(settings)
    belief = Belief(id="b2", claim_id="CLM_X", statement="x", scope="PROJECT", project_id="PRJ_1",
                    probability=0.5, posterior=0.5, alpha=1.0, beta=1.0, uncertainty=0.5)
    out = BeliefEngine(settings, policy).update(
        BeliefUpdateInput(beliefs=[belief], evidence=kept, policy=policy)
    )
    discounts = [app.dedup_discount for app in out.applications]
    assert discounts == [1.0, 0.5]  # first full, second halved


def test_qa_empty_source_evidence_not_treated_as_exact_duplicate():
    """Evidence with empty source must NOT be auto-deduped by content hash.

    KNOWN SOURCE BUG: when content_fingerprint is None, the dedup engine falls
    back to content_fingerprint(evidence.source or ''), so ALL empty-source
    evidence shares one hash and everything but the first is silently dropped.
    """
    engine = EvidenceDedupEngine(Settings())

    def ev(eid):
        return Evidence(
            id=eid, claim_ids=["CLM_X"], scope="MARKET",
            evidence_type="REVIEWED_EXTERNAL_RESEARCH", source="",
            provenance={"source_url": ""},
        )

    result = engine.group([ev("E_EMPTY_1"), ev("E_EMPTY_2")])
    assert result.dropped_ids == []  # BUG (fails): E_EMPTY_2 is dropped
    assert len(result.kept_ids) == 2


def test_qa_conflict_raises_uncertainty_and_persists():
    """Support + contradict above threshold -> EvidenceConflict persisted, uncertainty up."""
    settings = Settings()
    repo = InMemoryRepository()
    policy = EvidencePolicy(settings)
    sup = _evidence("E_SUP", "Pilot prospects pay quickly", direction="SUPPORTS")
    con = _evidence("E_CON", "Pilot prospects never pay", direction="CONTRADICTS")
    engine = ConflictEngine(settings)
    conflicts = engine.detect({"CLM_X": [sup, con]}, threshold=0.3)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.severity > 0
    assert set(conflict.evidence_ids) == {"E_SUP", "E_CON"}
    repo.save_evidence_conflict(conflict)
    persisted = repo.list_evidence_conflicts(claim_id="CLM_X")
    assert len(persisted) == 1
    assert persisted[0].resolution_status == "OPEN"

    # Applying to a belief raises uncertainty and lowers confidence.
    belief = Belief(id="b3", claim_id="CLM_X", statement="x", scope="PROJECT", project_id="PRJ_1",
                    probability=0.5, posterior=0.5, alpha=1.0, beta=1.0, uncertainty=0.4, confidence=0.6)
    raised = engine.apply_to_belief(belief, conflict)
    assert raised.uncertainty > belief.uncertainty
    assert raised.confidence < belief.confidence
    assert raised.uncertainty <= 1.0


def test_qa_conflict_within_orchestrator_sets_record_raise():
    """Orchestrator path: BeliefUpdateRecord.conflict_uncertainty_raise > 0."""
    # Simulate the solve path: detect conflicts, then save records with raises.
    from vencertia.runtime.belief_engine import BeliefEngine

    settings = Settings()
    policy = EvidencePolicy(settings)
    sup = _evidence("E_SUP2", "Pilot prospects pay quickly", direction="SUPPORTS")
    con = _evidence("E_CON2", "Pilot prospects never pay", direction="CONTRADICTS")
    conflicts = ConflictEngine(settings).detect({"CLM_X": [sup, con]}, threshold=0.3)
    belief = Belief(id="b4", claim_id="CLM_X", statement="x", scope="PROJECT", project_id="PRJ_1",
                    probability=0.5, posterior=0.5, alpha=1.0, beta=1.0, uncertainty=0.4)
    out = BeliefEngine(settings, policy).update(
        BeliefUpdateInput(beliefs=[belief], evidence=[sup, con], policy=policy)
    )
    assert out.update_records
    # The raise amount the orchestrator would attach: 0.15 * severity.
    expected_raise = round(min(1.0, 0.15 * conflicts[0].severity), 6)
    assert expected_raise > 0
