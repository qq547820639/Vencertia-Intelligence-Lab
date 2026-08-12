"""Convergence: report + critical uncertainties."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import ConvergenceStatus, VencertiaBaseModel, utcnow


class CriticalUncertainty(VencertiaBaseModel):
    belief_id: str
    statement: str = ""
    impact: float = 0.0  # |coef(best,b) − coef(second,b)| × uncertainty(b)
    uncertainty: float = 0.0
    coefficient_delta: float = 0.0


class ConvergenceReport(VencertiaBaseModel):
    decision_id: str
    status: ConvergenceStatus = ConvergenceStatus.NOT_CONVERGED
    reason: str = ""
    critical_uncertainties: list[CriticalUncertainty] = Field(default_factory=list)
    next_step: str | None = None
    checked_at: datetime = Field(default_factory=utcnow)
