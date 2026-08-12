"""QA adversarial tests — Belief trace/version + calibration honesty (P0).

Verifies: posterior_version increments, BeliefUpdateRecord is persisted with
old/new/discounts, and calibration under-sampling reports UNCALIBRATED instead
of fabricating a value.
"""

from __future__ import annotations

import pytest

from vencertia.config import Settings
from vencertia.domain import Belief, Evidence, Scope
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.belief_engine import BeliefEngine, BeliefUpdateInput
from vencertia.runtime.calibration_engine import CalibrationEngine
from vencertia.runtime.confidence_calibrator import ConfidenceCalibrator
from vencertia.runtime.evidence_policy import EvidencePolicy


def _evidence(eid, claim_ids, direction="SUPPORTS", strength=0.9, reliability=0.9) -> Evidence:
    return Evidence(
        id=eid, claim_ids=claim_ids, scope=Scope.PROJECT,
        evidence_type="OBSERVED_BEHAVIOR", source=eid,
        supports_or_contradicts=direction, strength=strength, reliability=reliability,
    )


def _belief(bid="wtp", claim_id="CLM_WTP", p=0.5):
    return Belief(
        id=bid, claim_id=claim_id, statement=claim_id, scope=Scope.PROJECT,
        project_id="PRJ_QA", probability=p, posterior=p, alpha=1.0, beta=1.0,
        uncertainty=0.5, decision_relevant=True,
    )


def test_qa_belief_update_increments_version_and_persists_record():
    repo = InMemoryRepository()
    settings = Settings()
    policy = EvidencePolicy(settings)
    belief = _belief(p=0.5)
    engine = BeliefEngine(settings, policy)

    output = engine.update(
        BeliefUpdateInput(
            beliefs=[belief],
            evidence=[_evidence("E_A", ["CLM_WTP"]), _evidence("E_B", ["CLM_WTP"])],
            policy=policy,
        )
    )
    updated = output.beliefs[0]
    # Two applications in one batch -> posterior_version advances beyond 1.
    assert updated.posterior_version > 1
    assert updated.previous_snapshot is not None
    snap = updated.previous_snapshot
    assert snap["probability"] == pytest.approx(0.5)
    assert "alpha" in snap and "beta" in snap

    # One update record per belief per batch, with old/new + discounts.
    assert len(output.update_records) == 1
    rec = output.update_records[0]
    assert rec.belief_id == "wtp"
    assert rec.old_probability == pytest.approx(0.5)
    assert rec.new_probability == pytest.approx(updated.probability)
    assert rec.old_uncertainty >= 0
    assert rec.new_uncertainty >= 0
    assert set(rec.evidence_used) == {"E_A", "E_B"}
    assert rec.effective_weight > 0
    assert rec.freshness_discount == pytest.approx(1.0)
    assert rec.correlation_discount <= 1.0
    assert rec.posterior_version == updated.posterior_version
    assert rec.policy_version == "1.1"

    # Persisted through the repository.
    repo.save_belief_update_record(rec)
    history = repo.list_belief_update_records("wtp")
    assert len(history) == 1
    assert history[0].new_probability == pytest.approx(rec.new_probability)


def test_qa_belief_update_record_has_conflict_raise_slot():
    """BeliefUpdateRecord supports conflict_uncertainty_raise (v1.1 field)."""
    settings = Settings()
    policy = EvidencePolicy(settings)
    belief = _belief(p=0.5)
    output = BeliefEngine(settings, policy).update(
        BeliefUpdateInput(beliefs=[belief], evidence=[_evidence("E_C", ["CLM_WTP"])], policy=policy)
    )
    assert output.update_records[0].conflict_uncertainty_raise == pytest.approx(0.0)
    # The orchestrator path adds the raise (covered in solve); field is present.
    assert "conflict_uncertainty_raise" in output.update_records[0].model_dump()


def test_qa_calibration_under_sampling_is_uncalibrated():
    """Insufficient samples -> UNCALIBRATED with calibrated=None (no fabrication)."""
    repo = InMemoryRepository()
    settings = Settings()
    cal_engine = CalibrationEngine(settings)
    calibrator = ConfidenceCalibrator(calibration_engine=cal_engine, repo=repo, settings=settings)
    result = calibrator.calibrate(0.7, "default")
    assert result.status == "UNCALIBRATED"
    assert result.calibrated is None
    assert result.raw == pytest.approx(0.7)
    assert result.n < 20


def test_qa_calibration_corrects_when_sufficient_samples():
    """With enough resolved predictions, calibration actually maps raw->calibrated."""
    repo = InMemoryRepository()
    settings = Settings()
    cal_engine = CalibrationEngine(settings)
    calibrator = ConfidenceCalibrator(calibration_engine=cal_engine, repo=repo, settings=settings, min_samples=3)
    # Register 3 predictions and resolve them with a biased outcome pattern.
    from vencertia.domain import Decision, DecisionOption, PredictionEntry, utcnow

    decision = Decision(
        id="DEC_CAL", decision_question="q", objective_id="OBJ_CAL", project_id="PRJ_CAL",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"],
    )
    for i, p in enumerate([0.9, 0.8, 0.7]):
        entry = PredictionEntry(
            id=f"PRD_CAL_{i}", project_id="PRJ_CAL", claim_id="CLM_WTP",
            target="t", predicted_probability=p, due_at=utcnow(),
        )
        repo.save_prediction(entry)
        repo.save_prediction(
            entry.model_copy(
                update={
                    "resolution": "FALSE", "outcome": False, "resolved_at": utcnow(),
                    "snapshot_verified": True, "version": entry.version + 1,
                }
            )
        )
    result = calibrator.calibrate(0.85, "default")
    assert result.status == "CALIBRATED"
    assert result.calibrated is not None
