"""QA adversarial tests — Requirement 9: Benchmark reproducible; L0 is clearly
distinguished from real predictive capability (documentation statement)."""

from __future__ import annotations

from pathlib import Path

from vencertia.benchmark.l0 import L0Runner


def test_l0_reproducible_two_runs(project_root: Path) -> None:
    """Running L0 twice must produce byte-identical pass rates and case statuses."""
    runner = L0Runner()
    path = project_root / "data/benchmarks/l0_cases.json"
    first = runner.run_file(path)
    second = runner.run_file(path)
    assert first.pass_rate == second.pass_rate
    assert first.failed == second.failed
    assert [(c.id, c.correct, c.status) for c in first.cases] == [
        (c.id, c.correct, c.status) for c in second.cases
    ]


def test_l0_is_synthetic_source(project_root: Path) -> None:
    """L0 is explicitly a synthetic regression, not a claim of real-world prediction."""
    runner = L0Runner()
    report = runner.run_file(project_root / "data/benchmarks/l0_cases.json")
    assert report.source == "synthetic"
    assert report.level == "L0"


def test_benchmark_docs_distinguish_synthetic_from_predictive(project_root: Path) -> None:
    """docs/BENCHMARK.md must frame L0 as regression (not real predictive power)."""
    doc = (project_root / "docs" / "BENCHMARK.md").read_text(encoding="utf-8")
    assert "synthetic" in doc.lower()
    assert "regression" in doc.lower()
    # L1 uses historical time-sliced replay with leakage discipline.
    assert "time-sliced" in doc.lower()
    assert "leakage" in doc.lower()
