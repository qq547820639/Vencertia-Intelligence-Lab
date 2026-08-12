"""CalibrationEngine tests: Brier, ECE, stratification, settled-only."""

from __future__ import annotations

from vencertia.domain import CalibrationScope, PredictionEntry, utcnow
from vencertia.runtime.calibration_engine import CalibrationEngine, CalibrationInput


def _entry(pid, prob, outcome=None, resolution="OPEN", model="m1", domain="b2b-saas",
           module="decision", policy="1.0") -> PredictionEntry:
    return PredictionEntry(
        id=pid,
        project_id="PRJ_1",
        claim_id="CLM_1",
        target="t",
        predicted_probability=prob,
        policy_version=policy,
        model_tag=model,
        domain=domain,
        module_tag=module,
        due_at=utcnow(),
        resolution=resolution,
        outcome=outcome,
        resolved_at=utcnow() if outcome is not None else None,
    )


def test_brier_hand_computed():
    engine = CalibrationEngine()
    rows = [
        _entry("p1", 0.9, True, "TRUE"),
        _entry("p2", 0.8, True, "TRUE"),
        _entry("p3", 0.2, False, "FALSE"),
        _entry("p4", 0.1, False, "FALSE"),
    ]
    profile = engine.report(CalibrationInput(rows, bins=5))
    expected_brier = ((0.9 - 1) ** 2 + (0.8 - 1) ** 2 + (0.2 - 0) ** 2 + (0.1 - 0) ** 2) / 4
    assert abs(profile.brier_score - expected_brier) < 1e-9
    assert profile.n == 4


def test_ece_hand_computed():
    engine = CalibrationEngine()
    rows = [
        _entry("p1", 0.9, True, "TRUE"),
        _entry("p2", 0.1, False, "FALSE"),
    ]
    profile = engine.report(CalibrationInput(rows, bins=10))
    # [0.9,1.0) bucket: conf=0.9 rate=1.0 gap=0.1; [0.1,0.2): conf=0.1 rate=0 gap=0.1
    assert abs(profile.expected_calibration_error - 0.1) < 1e-9


def test_only_settled_counted():
    engine = CalibrationEngine()
    rows = [
        _entry("p1", 0.9, True, "TRUE"),
        _entry("p2", 0.7, None, "OPEN"),
        _entry("p3", 0.6, None, "CANCELLED"),
    ]
    profile = engine.report(CalibrationInput(rows, bins=5))
    assert profile.n == 1


def test_stratified_scopes():
    engine = CalibrationEngine()
    rows = [
        _entry("p1", 0.9, True, "TRUE", model="m1", domain="b2b-saas", module="decision"),
        _entry("p2", 0.1, False, "FALSE", model="m2", domain="consumer", module="belief"),
    ]
    profiles = engine.update_all_scopes(rows)
    scopes = {(p.scope, p.scope_key) for p in profiles}
    assert ("ALL", "ALL") in scopes
    assert ("MODEL", "m1@1.0") in scopes
    assert ("DOMAIN", "b2b-saas") in scopes
    assert ("MODULE", "decision") in scopes
    assert ("MODULE", "belief") in scopes


def test_empty_report():
    engine = CalibrationEngine()
    profile = engine.report(CalibrationInput([]))
    assert profile.n == 0
    assert profile.brier_score is None
