"""Calibration profiles (Brier / ECE / buckets / stratification)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class CalibrationScope(str, Enum):
    ALL = "ALL"
    MODEL = "MODEL"  # by model_tag
    DOMAIN = "DOMAIN"  # by domain
    MODULE = "MODULE"  # by engine/module


class CalibrationProfile(VencertiaBaseModel):
    id: str  # CAL_...
    scope: CalibrationScope = CalibrationScope.ALL
    scope_key: str = "ALL"
    n: int = 0
    brier_score: float | None = None
    expected_calibration_error: float | None = None
    mean_confidence: float | None = None
    empirical_rate: float | None = None
    bins: list[dict] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
