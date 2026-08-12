"""Benchmark tests: L0 suite passes 24+, L1 leakage audit, metrics."""

from __future__ import annotations

from pathlib import Path

from vencertia.benchmark.l0 import L0Runner
from vencertia.benchmark.l1 import L1Runner
from vencertia.benchmark.metrics import (
    compute_abstention_quality,
    compute_brier,
    compute_decision_accuracy,
    compute_ece,
)


def test_l0_suite_passes(project_root: Path):
    runner = L0Runner()
    report = runner.run_file(project_root / "data/benchmarks/l0_cases.json")
    assert report.n >= 24
    assert report.failed == 0
    assert report.pass_rate == 1.0


def test_l0_covers_categories(project_root: Path):
    runner = L0Runner()
    report = runner.run_file(project_root / "data/benchmarks/l0_cases.json")
    statuses = {c.status for c in report.cases}
    assert "ABSTAIN" in statuses
    assert "GO" in statuses
    assert "KILL" in statuses
    assert "PIVOT" in statuses
    assert "HOLD" in statuses


def test_legacy_l0_baseline_runs(project_root: Path):
    runner = L0Runner()
    report = runner.run_legacy_file(project_root / "data/benchmarks/v0.2.jsonl")
    assert report.n == 24


def test_l1_leakage_rejection(project_root: Path):
    runner = L1Runner()
    report = runner.run(project_root / "data/benchmarks/l1_cases.jsonl")
    assert "l1-07-leak" in report.rejected
    assert all(c.id != "l1-07-leak" for c in report.cases)
    assert report.failed == 0


def test_metric_decision_accuracy():
    assert compute_decision_accuracy(["a", "b"], ["a", "b"]) == 1.0
    assert compute_decision_accuracy(["a", "b"], ["a", "c"]) == 0.5


def test_metric_abstention_quality():
    q = compute_abstention_quality([True, True, False], [True, False, True])
    assert abs(q["coverage"] - 2 / 3) < 1e-5
    assert abs(q["selective_accuracy"] - 0.5) < 1e-5
    assert abs(q["quality"] - (2 / 3 * 0.5)) < 1e-5


def test_metric_brier():
    assert abs(compute_brier([0.9, 0.1], [1, 0]) - 0.01) < 1e-9
    assert abs(compute_brier([0.5, 0.5], [1, 0]) - 0.25) < 1e-9


def test_metric_ece():
    # Perfect calibration -> ECE 0
    assert abs(compute_ece([0.9, 0.1], [1, 0], bins=10) - 0.1) < 1e-9
