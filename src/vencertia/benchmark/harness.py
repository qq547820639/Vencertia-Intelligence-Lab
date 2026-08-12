"""Benchmark harness — shared report models + comparison skeleton."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from vencertia.domain.base import VencertiaBaseModel


class BenchmarkCaseResult(VencertiaBaseModel):
    id: str
    predicted_option: str
    gold_option: str
    decided: bool
    correct: bool
    status: str = ""
    gold_status: str | None = None  # v1.1.2: gold decision status label
    confidence: float | None = None
    margin: float | None = None
    predicted_experiment: str | None = None
    gold_experiment: str | None = None
    experiment_correct: bool | None = None
    predicted_critical: str | None = None
    gold_critical: str | None = None
    critical_correct: bool | None = None
    # v1.1.2 (P1-10): float|None — None means "no utility label" (L1) so
    # regret is N/A instead of a fake 0.
    chosen_utility: float | None = None
    best_utility: float | None = None
    notes: str = ""


class BenchmarkReport(BaseModel):
    level: str  # L0 | L1
    source: str = ""
    n: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    metrics: dict[str, Any] = Field(default_factory=dict)
    cases: list[BenchmarkCaseResult] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)  # rejected case ids (e.g. leakage)
    comparison: dict[str, Any] | None = None


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


def oss_admission_experiment(
    baseline: BenchmarkReport,
    candidate: BenchmarkReport,
    frozen_cases: list[str],
) -> dict:
    """OSS admission experiment (ADR-006): compare frozen-case deltas.

    Returns the admission verdict. A candidate is ADMITTED when it does not
    regress on any frozen case AND its overall pass rate is not lower than the
    baseline. Deliberate degradation on a frozen case yields CANDIDATE_REJECTED.
    """
    base_by_id = {c.id: c for c in baseline.cases}
    cand_by_id = {c.id: c for c in candidate.cases}
    regressions: list[str] = []
    frozen_present = 0
    for case_id in frozen_cases:
        if case_id not in base_by_id or case_id not in cand_by_id:
            continue
        frozen_present += 1
        base_ok = base_by_id[case_id].correct
        cand_ok = cand_by_id[case_id].correct
        if base_ok and not cand_ok:
            regressions.append(case_id)
    admitted = not regressions and candidate.pass_rate >= baseline.pass_rate
    notes: list[str] = []
    if not frozen_cases:
        notes.append("No frozen cases provided; admission based on pass rate only.")
    if regressions:
        notes.append(f"Frozen-case regressions: {', '.join(regressions)}")
    return {
        "baseline": {"pass_rate": baseline.pass_rate, "n": baseline.n},
        "candidate": {"pass_rate": candidate.pass_rate, "n": candidate.n},
        "delta": {"pass_rate": round(candidate.pass_rate - baseline.pass_rate, 6)},
        "admission": "CANDIDATE_ADMITTED" if admitted else "CANDIDATE_REJECTED",
        "frozen_case_count": frozen_present,
        "notes": notes,
    }
