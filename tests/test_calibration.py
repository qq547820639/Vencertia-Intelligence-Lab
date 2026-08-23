"""CalibrationEngine tests: Brier, ECE, stratification, settled-only."""

from __future__ import annotations

from vencertia.domain import PredictionEntry, utcnow
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


# -- piecewise mapping edge cases (v2.0.1 direction-reversal regression) ------


def test_map_piecewise_below_lowest_bucket_clamps_to_lowest_rate():
    """Bins not covering the low range must NOT map low raw to the TOP rate.

    Regression: raw=0.05 with buckets starting at 0.4 fell through the loop
    and returned the last bucket's empirical rate (0.05 -> 0.95).
    """
    bins = [
        {"lo": 0.4, "hi": 0.5, "mean_confidence": 0.45, "empirical_rate": 0.30},
        {"lo": 0.9, "hi": 1.0, "mean_confidence": 0.95, "empirical_rate": 0.95},
    ]
    mapped = CalibrationEngine._map_piecewise(0.05, bins)
    assert mapped == 0.30  # clamped to the LOWEST bucket, never the highest


def test_map_piecewise_zero_raw_stays_low():
    bins = [
        {"lo": 0.8, "hi": 0.9, "mean_confidence": 0.85, "empirical_rate": 0.90},
    ]
    assert CalibrationEngine._map_piecewise(0.0, bins) == 0.90  # only bucket wins
    assert CalibrationEngine._map_piecewise(1.0, bins) == 0.90  # high end unchanged


def test_map_piecewise_high_end_behavior_unchanged():
    """Above the highest bucket the existing hold-constant behavior stays."""
    bins = [
        {"lo": 0.1, "hi": 0.2, "mean_confidence": 0.15, "empirical_rate": 0.10},
        {"lo": 0.8, "hi": 0.9, "mean_confidence": 0.85, "empirical_rate": 0.90},
    ]
    assert CalibrationEngine._map_piecewise(0.99, bins) == 0.90
    assert CalibrationEngine._map_piecewise(0.85, bins) == 0.90


def test_map_piecewise_monotonic_when_buckets_monotonic():
    """With well-ordered buckets the mapping must be non-decreasing.

    (Inverted adjacent buckets are allowed to be non-monotonic — no isotonic
    constraint is imposed; only the low-end direction reversal is fixed.)
    """
    bins = [
        {"lo": 0.1, "hi": 0.2, "mean_confidence": 0.15, "empirical_rate": 0.10},
        {"lo": 0.4, "hi": 0.5, "mean_confidence": 0.45, "empirical_rate": 0.40},
        {"lo": 0.8, "hi": 0.9, "mean_confidence": 0.85, "empirical_rate": 0.90},
    ]
    raws = [0.0, 0.05, 0.15, 0.3, 0.45, 0.65, 0.85, 0.95, 1.0]
    mapped = [CalibrationEngine._map_piecewise(r, bins) for r in raws]
    assert mapped == sorted(mapped)
    assert mapped[0] <= mapped[-1]


def test_calibrate_low_raw_not_mapped_to_high_rate():
    """End-to-end: a 0.05 raw confidence must not come back near 0.95."""
    engine = CalibrationEngine()
    rows = [
        _entry("p1", 0.45, False, "FALSE"),  # low bucket: hit rate 0.0
        _entry("p2", 0.90, True, "TRUE"),  # high bucket: hit rate 1.0
    ]
    result = engine.calibrate(0.05, predictions=rows, min_samples=1)
    assert result.status == "CALIBRATED"
    # Clamped to the LOWEST bucket's rate (0.0), not the top bucket's (1.0).
    assert result.calibrated == 0.0
