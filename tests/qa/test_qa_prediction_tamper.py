"""QA adversarial tests — Requirement 7: Prediction settlement is real & tamper-proof.

- resolve 后 original probability 不可改 (irreversible settlement).
- snapshot hash verification detects tampering.
- A second adversarial test exposes that PredictionLedger.resolve never
  populates resolved_at (minor bug).
"""

from __future__ import annotations

import pytest

from vencertia.domain import Belief, Decision, DecisionOption
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.prediction_ledger import PredictionLedger


def _belief() -> Belief:
    return Belief(
        id="wtp", claim_id="CLM_wtp", statement="wtp", scope="PROJECT",
        project_id="PRJ_1", posterior=0.7, probability=0.7, alpha=7, beta=3,
        decision_relevant=True,
    )


def _decision() -> Decision:
    return Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"], horizon="short",
    )


def test_resolve_preserves_original_probability() -> None:
    repo = InMemoryRepository()
    ledger = PredictionLedger(repo)
    entry = ledger.register(_decision(), [_belief()])[0]
    resolved = ledger.resolve(entry.id, True)
    assert resolved.predicted_probability == 0.7
    stored = repo.get_prediction(entry.id)
    assert stored.predicted_probability == 0.7  # frozen in repo too
    assert stored.resolution == "TRUE"
    assert stored.snapshot_verified is True


def test_double_resolve_raises() -> None:
    repo = InMemoryRepository()
    ledger = PredictionLedger(repo)
    entry = ledger.register(_decision(), [_belief()])[0]
    ledger.resolve(entry.id, True)
    with pytest.raises(ValueError):
        ledger.resolve(entry.id, False)


def test_post_resolve_tamper_is_detected_by_hash() -> None:
    """Tampering with the stored probability after settlement breaks verify_snapshot."""
    repo = InMemoryRepository()
    ledger = PredictionLedger(repo)
    entry = ledger.register(_decision(), [_belief()])[0]
    ledger.resolve(entry.id, True)
    stored = repo.get_prediction(entry.id)
    tampered = stored.model_copy(
        update={
            "predicted_probability": 0.99,
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
    assert ledger.verify_snapshot(repo.get_prediction(entry.id)) is False


def test_resolve_populates_resolved_at() -> None:
    """Settlement must record when it happened (resolved_at non-None).

    Currently PredictionLedger.resolve copies resolved_at=None from the open
    entry, so the settled prediction has no resolution timestamp — see QA report
    (MINOR). This test pins the required behavior.
    """
    repo = InMemoryRepository()
    ledger = PredictionLedger(repo)
    entry = ledger.register(_decision(), [_belief()])[0]
    resolved = ledger.resolve(entry.id, True)
    assert resolved.resolution == "TRUE"
    assert resolved.resolved_at is not None, "settled prediction must have resolved_at"
