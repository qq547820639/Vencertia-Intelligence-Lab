"""PredictionLedger tests: snapshots, irreversibility, tamper detection."""

from __future__ import annotations

import pytest

from vencertia.domain import Belief, Decision, DecisionOption
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.prediction_ledger import PredictionLedger


def _belief(bid, p, alpha, beta) -> Belief:
    return Belief(
        id=bid, claim_id="CLM_" + bid, statement=bid, scope="PROJECT",
        project_id="PRJ_1", posterior=p, probability=p, alpha=alpha, beta=beta,
        decision_relevant=True,
    )


def _decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"],
        horizon="short",
    )


def test_register_creates_snapshot(repo):
    ledger = PredictionLedger(repo)
    entries = ledger.register(_decision(), [_belief("wtp", 0.7, 7, 3)])
    assert len(entries) == 1
    entry = entries[0]
    assert entry.context_snapshot_hash
    assert entry.policy_version == "1.0"
    assert entry.belief_snapshot["wtp"]["probability"] == 0.7


def test_register_then_modify_belief_does_not_change_snapshot(repo):
    ledger = PredictionLedger(repo)
    beliefs = [_belief("wtp", 0.7, 7, 3)]
    entries = ledger.register(_decision(), beliefs)
    entry = entries[0]
    # Modify the belief after registration.
    beliefs[0].posterior = 0.1
    stored = repo.get_prediction(entry.id)
    assert stored.belief_snapshot["wtp"]["probability"] == 0.7  # frozen


def test_resolve_is_irreversible(repo):
    ledger = PredictionLedger(repo)
    entry = ledger.register(_decision(), [_belief("wtp", 0.7, 7, 3)])[0]
    resolved = ledger.resolve(entry.id, True)
    assert resolved.resolution == "TRUE"
    assert resolved.outcome is True
    assert resolved.predicted_probability == 0.7  # original unchanged
    with pytest.raises(ValueError):
        ledger.resolve(entry.id, False)  # already settled


def test_tampered_snapshot_marks_cancelled(repo):
    ledger = PredictionLedger(repo)
    entry = ledger.register(_decision(), [_belief("wtp", 0.7, 7, 3)])[0]
    # Tamper with the stored snapshot in the repo.
    stored = repo.get_prediction(entry.id)
    tampered = stored.model_copy(
        update={
            "belief_snapshot": {"wtp": {"probability": 0.99, "uncertainty": 0.1,
                                         "alpha": 99, "beta": 1}},
            "version": stored.version,
        }
    )
    repo._data[("prediction", entry.id)] = {
        "payload": tampered.model_dump(mode="json"),
        "version": tampered.version,
        "updated_at": "x",
    }
    with pytest.warns(RuntimeWarning):
        resolved = ledger.resolve(entry.id, True)
    assert resolved.resolution == "CANCELLED"
    assert resolved.snapshot_verified is False


def test_verify_snapshot_cross_check(repo):
    ledger = PredictionLedger(repo)
    beliefs = [_belief("wtp", 0.7, 7, 3)]
    entry = ledger.register(_decision(), beliefs)[0]
    assert ledger.verify_snapshot(entry) is True
    # Context drift: different belief values -> verification False.
    drifted = [_belief("wtp", 0.9, 9, 1)]
    assert ledger.verify_snapshot(entry, beliefs=drifted) is False


def test_resolve_writes_aware_utc_resolved_at(repo):
    """Defect-2 regression: resolve() must set resolved_at (aware UTC)."""
    ledger = PredictionLedger(repo)
    entry = ledger.register(_decision(), [_belief("wtp", 0.7, 7, 3)])[0]
    assert entry.resolved_at is None
    resolved = ledger.resolve(entry.id, True)
    assert resolved.resolved_at is not None
    assert resolved.resolved_at.tzinfo is not None  # aware, not naive
    assert resolved.resolution == "TRUE"


def test_repo_resolve_prediction_uses_aware_utc(repo):
    """Defect-2 regression: repository resolve path also writes aware UTC."""
    from vencertia.domain import PredictionEntry

    entry = PredictionEntry(id="PRD_TZ", project_id="PRJ_1", target="t", predicted_probability=0.6)
    repo.save_prediction(entry)
    resolved = repo.resolve_prediction("PRD_TZ", True)
    assert resolved.resolved_at is not None
    assert resolved.resolved_at.tzinfo is not None
    assert resolved.resolved_at.utcoffset() is not None
