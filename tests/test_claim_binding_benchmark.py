"""Synthetic Claim Binding Benchmark tests (GAP-04)."""

from __future__ import annotations

import json
from pathlib import Path

from vencertia.benchmark.claim_binding import (
    CATEGORIES,
    ClaimBindingBenchmarkRunner,
)


def _cases(project_root: Path) -> list[dict]:
    path = project_root / "data/benchmarks/claim_binding_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_benchmark_has_30_40_cases(project_root: Path) -> None:
    cases = _cases(project_root)
    assert 30 <= len(cases) <= 40, len(cases)


def test_benchmark_covers_all_14_categories(project_root: Path) -> None:
    categories = {c["category"] for c in _cases(project_root)}
    assert categories == set(CATEGORIES), set(CATEGORIES) - categories


def test_benchmark_runs_and_outputs_8_metrics(project_root: Path) -> None:
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run(project_root / "data/benchmarks/claim_binding_cases.json")
    assert report.n == len(_cases(project_root))
    assert report.synthetic is True
    for name in (
        "precision",
        "recall",
        "f1",
        "unbound_accuracy",
        "ambiguous_accuracy",
        "rejected_accuracy",
        "multi_claim_exact_match",
        "multi_claim_partial_match",
        "coverage",
    ):
        assert name in report.metrics, name
    # Every metric is either a number or None (N/A), never faked as 0.0.
    for value in report.metrics.values():
        assert value is None or (isinstance(value, float) and 0.0 <= value <= 1.0)


def test_benchmark_is_deterministic(project_root: Path) -> None:
    runner = ClaimBindingBenchmarkRunner()
    r1 = runner.run(project_root / "data/benchmarks/claim_binding_cases.json")
    r2 = runner.run(project_root / "data/benchmarks/claim_binding_cases.json")
    assert [c.predicted_status for c in r1.cases] == [c.predicted_status for c in r2.cases]
    assert [c.predicted_claim_ids for c in r1.cases] == [c.predicted_claim_ids for c in r2.cases]
    assert r1.metrics == r2.metrics


def test_benchmark_known_limitation_is_reported_not_hidden(project_root: Path) -> None:
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run(project_root / "data/benchmarks/claim_binding_cases.json")
    limitations = [r for r in report.cases if r.known_limitation]
    assert limitations, "expected at least one documented known limitation"
    for r in limitations:
        assert r.correct is False  # honestly marked as not passing
        assert r.reason  # with an explanation


def test_benchmark_all_non_limitation_cases_pass(project_root: Path) -> None:
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run(project_root / "data/benchmarks/claim_binding_cases.json")
    unexpected = [r for r in report.cases if not r.correct and not r.known_limitation]
    assert unexpected == [], [r.id for r in unexpected]


def test_division_by_zero_guard_returns_none():
    """A benchmark with no ambiguous cases reports ambiguous_accuracy as N/A."""
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run_cases(
        [
            {
                "id": "CB-Z1",
                "category": "single_match",
                "evidence": {"id": "E_Z1", "scope": "MARKET",
                             "source": "ICP will pay for the promised outcome"},
                "claims": [{"id": "CLM_1", "statement": "ICP will pay for the promised outcome",
                            "scope": "PROJECT"}],
                "gold_status": "BOUND",
                "gold_claim_ids": ["CLM_1"],
                "config": {},
            }
        ]
    )
    assert report.metrics["ambiguous_accuracy"] is None  # zero denominator → N/A
    assert report.metrics["rejected_accuracy"] is None
    assert report.metrics["multi_claim_exact_match"] is None
    assert report.metrics["multi_claim_partial_match"] is None
    assert report.metrics["precision"] is not None


def test_render_marks_synthetic():
    runner = ClaimBindingBenchmarkRunner()
    report = runner.run_cases([])
    text = runner.render(report)
    assert "Synthetic Claim Binding Benchmark" in text
    assert "NOT real-world accuracy" in text
