"""v2.0.1 regression — manually entered evidence must reach the BeliefEngine.

Previously POST /v1/evidence and EvidenceImporter.import_batch only graded +
persisted evidence; bound evidence never updated the belief of its claim, so
re-evaluation after entering VERIFIED/CONTRADICTS evidence left the belief
unchanged.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.domain import Belief, Claim, Direction, Evidence, Scope
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import (
    EvidenceDedupEngine,
    EvidenceImporter,
    SolveOrchestrator,
    default_engine_bundle,
)
from vencertia.runtime.belief_engine import BeliefEngine


def _seed_claim_and_belief(repo: InMemoryRepository, project_id: str = "PRJ_M") -> Belief:
    claim = Claim(
        id="CLM_WTP",
        project_id=project_id,
        statement="Customers will pay $50/mo",
        scope="PROJECT",
    )
    repo.add_claim(claim)
    belief = Belief(
        id="B_WTP",
        claim_id="CLM_WTP",
        statement="Customers will pay $50/mo",
        scope="PROJECT",
        project_id=project_id,
        posterior=0.7,
        probability=0.7,
        alpha=3.4,
        beta=2.6,
    )
    belief.uncertainty = 0.2
    belief.confidence = 0.8
    repo.save_belief(belief)
    return belief


def _contradicting_evidence(eid: str = "E_MANUAL") -> Evidence:
    return Evidence(
        id=eid,
        claim_ids=["CLM_WTP"],
        scope=Scope.PROJECT,
        evidence_type="EXPERIMENT_RESULT",
        source="Manual entry: paid pilot refused at $50/mo",
        project_id="PRJ_M",
        supports_or_contradicts=Direction.CONTRADICTS.value,
        directness=1.0,
        reliability=1.0,
        relevance=1.0,
        strength=0.9,
        verification="VERIFIED",
    )


# -- importer path -------------------------------------------------------------


def test_import_batch_updates_belief_for_bound_evidence(repo, policy, settings):
    belief = _seed_claim_and_belief(repo)
    before = repo.get_belief(belief.id).probability
    importer = EvidenceImporter(
        repo=repo,
        policy=policy,
        dedup=EvidenceDedupEngine(settings),
        belief_engine=BeliefEngine(settings, policy),
        settings=settings,
    )
    report = importer.import_batch([_contradicting_evidence()])
    assert report.imported == 1
    assert report.bound == 1

    after = repo.get_belief(belief.id)
    assert after.probability < before  # CONTRADICTS evidence lowered the posterior
    assert after.posterior_version > belief.posterior_version
    records = repo.list_belief_update_records(belief.id)
    assert records, "belief_update_records must be persisted for manual evidence"
    assert records[-1].evidence_used == ["E_MANUAL"]


def test_import_batch_without_belief_engine_keeps_legacy_behavior(repo, policy, settings):
    """No wired belief engine -> grade+persist only (legacy harnesses)."""
    belief = _seed_claim_and_belief(repo)
    importer = EvidenceImporter(
        repo=repo, policy=policy, dedup=EvidenceDedupEngine(settings)
    )
    report = importer.import_batch([_contradicting_evidence()])
    assert report.imported == 1
    assert repo.get_belief(belief.id).probability == 0.7


def test_import_batch_unbound_evidence_does_not_touch_beliefs(repo, policy, settings):
    belief = _seed_claim_and_belief(repo)
    importer = EvidenceImporter(
        repo=repo,
        policy=policy,
        dedup=EvidenceDedupEngine(settings),
        belief_engine=BeliefEngine(settings, policy),
        settings=settings,
    )
    unbound = _contradicting_evidence("E_ORPHAN").model_copy(update={"claim_ids": []})
    report = importer.import_batch([unbound])
    assert report.unbound == 1
    assert repo.get_belief(belief.id).probability == 0.7
    assert repo.list_belief_update_records(belief.id) == []


# -- API path ------------------------------------------------------------------


def _api_client_with_repo() -> tuple[TestClient, InMemoryRepository]:
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo,
        policy=engines.evidence_policy,
        engines=engines,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
        bus=bus,
        settings=settings,
    )
    return TestClient(create_app(settings, repo, runtime)), repo


def test_post_evidence_updates_belief():
    client, repo = _api_client_with_repo()
    belief = _seed_claim_and_belief(repo)
    before = repo.get_belief(belief.id).probability

    r = client.post("/v1/evidence", json={"evidence": _contradicting_evidence().model_dump(mode="json")})
    assert r.status_code == 200
    assert r.json()["code"] == 0

    after = repo.get_belief(belief.id)
    assert after.probability < before
    records = repo.list_belief_update_records(belief.id)
    assert records and records[-1].evidence_used == ["E_MANUAL"]


def test_post_evidence_policy_gate_still_authoritative():
    """REJECTED evidence still never persists (policy semantics unchanged)."""
    client, repo = _api_client_with_repo()
    belief = _seed_claim_and_belief(repo)
    gated = _contradicting_evidence("E_CASE").model_copy(
        update={"scope": "COMPANY_CASE", "transferability": None}
    )
    r = client.post("/v1/evidence", json={"evidence": gated.model_dump(mode="json")})
    assert r.status_code == 200  # prior-only gate, not a rejection
    # Prior-only company-case evidence must NOT move a PROJECT belief's counts.
    after = repo.get_belief(belief.id)
    assert after.alpha == 3.4 and after.beta == 2.6
