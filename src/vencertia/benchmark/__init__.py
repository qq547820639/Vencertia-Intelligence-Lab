"""Benchmark package — L0/L1 runners + metrics + harness."""

from __future__ import annotations

from vencertia.benchmark.harness import BenchmarkCaseResult, BenchmarkReport, comparison_report
from vencertia.benchmark.l0 import L0Case, L0Runner
from vencertia.benchmark.l1 import L1Case, L1Runner
from vencertia.benchmark.metrics import (
    compute_abstention_quality,
    compute_all,
    compute_brier,
    compute_critical_uncertainty_accuracy,
    compute_decision_accuracy,
    compute_decision_regret,
    compute_ece,
    compute_evidence_precision_recall,
    compute_experiment_selection_accuracy,
)

__all__ = [
    "BenchmarkCaseResult",
    "BenchmarkReport",
    "L0Case",
    "L0Runner",
    "L1Case",
    "L1Runner",
    "comparison_report",
    "compute_abstention_quality",
    "compute_all",
    "compute_brier",
    "compute_critical_uncertainty_accuracy",
    "compute_decision_accuracy",
    "compute_decision_regret",
    "compute_ece",
    "compute_evidence_precision_recall",
    "compute_experiment_selection_accuracy",
]
