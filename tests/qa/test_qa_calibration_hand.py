"""QA adversarial tests — Requirement 8: Brier + ECE exist and are correct.

Independent hand-computed values (different numbers from the engineer's suite)
prove the metric math, not just self-consistency.
"""

from __future__ import annotations

from vencertia.domain import CalibrationProfile, PredictionEntry, utcnow
from vencertia.runtime.calibration_engine import CalibrationEngine, CalibrationInput


def _entry(pid: str, prob: float, outcome: bool | None, resolution: str = "OPEN") -> PredictionEntry:
    return PredictionEntry(
        id=pid, project_id="PRJ_1", claim_id="CLM_1", target="t",
        predicted_probability=prob, policy_version="1.0", model_tag="m", domain="d",
        module_tag="decision", due_at=utcnow(), resolution=resolution,
        outcome=outcome, resolved_at=utcnow() if outcome is not None else None,
    )


def test_brier_hand_computed_independent() -> None:
    """Brier = mean((p - o)^2) for [0.7,0.4,0.9,0.2] vs [1,0,1,0] = 0.3/4 = 0.075."""
    rows = [
        _entry("p1", 0.7, True, "TRUE"),
        _entry("p2", 0.4, False, "FALSE"),
        _entry("p3", 0.9, True, "TRUE"),
        _entry("p4", 0.2, False, "FALSE"),
    ]
    profile = CalibrationEngine().report(CalibrationInput(rows, bins=5))
    expected = ((0.7 - 1) ** 2 + (0.4 - 0) ** 2 + (0.9 - 1) ** 2 + (0.2 - 0) ** 2) / 4
    assert abs(profile.brier_score - expected) < 1e-9
    assert abs(expected - 0.075) < 1e-9
    assert profile.n == 4


def test_ece_hand_computed_two_buckets() -> None:
    """ECE with two perfect points in distinct buckets is the binning gap (0.1 each)."""
    rows = [
        _entry("p1", 0.9, True, "TRUE"),
        _entry("p2", 0.1, False, "FALSE"),
    ]
    profile = CalibrationEngine().report(CalibrationInput(rows, bins=10))
    # bucket [0.9,1.0): conf 0.9 rate 1.0 gap 0.1, weight 0.5
    # bucket [0.1,0.2): conf 0.1 rate 0.0 gap 0.1, weight 0.5
    assert abs(profile.expected_calibration_error - 0.1) < 1e-9


def test_brier_only_settled_predictions() -> None:
    """OPEN/CANCELLED entries never enter calibration."""
    rows = [
        _entry("p1", 0.9, True, "TRUE"),
        _entry("p2", 0.7, None, "OPEN"),
        _entry("p3", 0.6, None, "CANCELLED"),
    ]
    profile = CalibrationEngine().report(CalibrationInput(rows, bins=5))
    assert profile.n == 1
    assert abs(profile.brier_score - (0.9 - 1) ** 2) < 1e-9


def test_metrics_reachable_through_runtime(repo) -> None:
    """Calibration profiles are produced by the engine bundle used in the runtime."""
    from vencertia.runtime import default_engine_bundle

    engines = default_engine_bundle(repo)
    rows = [
        _entry("p1", 0.8, True, "TRUE"),
        _entry("p2", 0.2, False, "FALSE"),
    ]
    profiles = engines.calibration_engine.update_all_scopes(rows)
    all_profile = next(p for p in profiles if p.scope == "ALL")
    assert isinstance(all_profile, CalibrationProfile)
    assert all_profile.n == 2
