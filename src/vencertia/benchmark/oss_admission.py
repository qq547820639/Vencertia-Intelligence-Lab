"""OSSAdmissionExperiment — frozen-case delta admission runner (ADR-006).

Runs the baseline and candidate implementations against the same frozen case
set, computes the delta, and emits ADMITTED / REJECTED. Deliberate degradation
on any frozen case must reject the candidate.
"""

from __future__ import annotations

from collections.abc import Callable

from vencertia.benchmark.harness import BenchmarkReport, oss_admission_experiment


class OSSAdmissionExperiment:
    """Runner that compares baseline vs candidate reports over frozen cases."""

    def __init__(
        self,
        frozen_cases: list[str],
        baseline_report: BenchmarkReport | None = None,
        candidate_report: BenchmarkReport | None = None,
    ) -> None:
        self.frozen_cases = frozen_cases
        self.baseline_report = baseline_report
        self.candidate_report = candidate_report

    def run(
        self,
        baseline_runner: Callable[[], BenchmarkReport],
        candidate_runner: Callable[[], BenchmarkReport],
    ) -> dict:
        """Execute both runners and compute the admission verdict."""
        baseline = self.baseline_report or baseline_runner()
        candidate = self.candidate_report or candidate_runner()
        return oss_admission_experiment(baseline, candidate, self.frozen_cases)
