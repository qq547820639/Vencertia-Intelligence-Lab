"""Benchmark harness — shared report models + comparison skeleton."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from vencertia.domain.base import VencertiaBaseModel


class BenchmarkCaseResult(VencertiaBaseModel):
    id: str
    predicted_option: str
    gold_option: str
    decided: bool
    correct: bool
    status: str = ""
    confidence: float | None = None
    margin: float | None = None
    predicted_experiment: str | None = None
    gold_experiment: str | None = None
    experiment_correct: bool | None = None
    predicted_critical: str | None = None
    gold_critical: str | None = None
    critical_correct: bool | None = None
    chosen_utility: float = 0.0
    best_utility: float = 0.0
    notes: str = ""


class BenchmarkReport(BaseModel):
    level: str  # L0 | L1
    source: str = ""
    n: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    metrics: Dict[str, Any] = Field(default_factory=dict)
    cases: List[BenchmarkCaseResult] = Field(default_factory=list)
    rejected: List[str] = Field(default_factory=list)  # rejected case ids (e.g. leakage)
    comparison: Dict[str, Any] | None = None


def comparison_report(baseline: BenchmarkReport, candidate: BenchmarkReport) -> dict:
    """Skeleton for baseline-vs-candidate comparison (ADR-006)."""
    return {
        "baseline": {
            "level": baseline.level,
            "pass_rate": baseline.pass_rate,
            "decision_accuracy": baseline.metrics.get("decision_accuracy"),
            "brier": baseline.metrics.get("brier"),
        },
        "candidate": {
            "level": candidate.level,
            "pass_rate": candidate.pass_rate,
            "decision_accuracy": candidate.metrics.get("decision_accuracy"),
            "brier": candidate.metrics.get("brier"),
        },
        "delta": {
            "pass_rate": round(candidate.pass_rate - baseline.pass_rate, 6),
            "decision_accuracy": (
                round(
                    (candidate.metrics.get("decision_accuracy") or 0.0)
                    - (baseline.metrics.get("decision_accuracy") or 0.0),
                    6,
                )
            ),
        },
        "admission": "CANDIDATE_ADMITTED"
        if candidate.pass_rate >= baseline.pass_rate
        else "CANDIDATE_REJECTED",
    }
