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


class CalibrationStatus(str, Enum):
    """Five-state calibration status + ``CALIBRATED`` legacy alias (V-1).

    The alias keeps old persisted JSON (``"CALIBRATED"``) deserializable; the
    calibration engine keeps emitting the legacy values for backward
    compatibility. The five-state vocabulary is consumed via
    :func:`classify_calibration`.
    """

    UNCALIBRATED = "UNCALIBRATED"
    LOW_SAMPLE = "LOW_SAMPLE"
    DOMAIN_CALIBRATED = "DOMAIN_CALIBRATED"
    USER_CALIBRATED = "USER_CALIBRATED"
    VALIDATED = "VALIDATED"
    CALIBRATED = "CALIBRATED"  # v1.1 compatibility alias


class EstimateType(str, Enum):
    """How a belief's probability estimate was produced (V-1)."""

    UNSPECIFIED = "UNSPECIFIED"
    ORDINAL_SUPPORT = "ORDINAL_SUPPORT"
    MODEL_SCORE = "MODEL_SCORE"
    CALIBRATED_PROBABILITY = "CALIBRATED_PROBABILITY"


def classify_calibration(n: int, min_samples: int = 20) -> CalibrationStatus:
    """Classify a calibration sample count into a :class:`CalibrationStatus`.

    ``n <= 0`` → UNCALIBRATED; ``0 < n < min_samples`` → LOW_SAMPLE;
    otherwise → DOMAIN_CALIBRATED.
    """
    if n <= 0:
        return CalibrationStatus.UNCALIBRATED
    if n < min_samples:
        return CalibrationStatus.LOW_SAMPLE
    return CalibrationStatus.DOMAIN_CALIBRATED


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


class CalibratedConfidence(VencertiaBaseModel):
    """Raw confidence with an optional calibrated correction (v1.1).

    ``status == UNCALIBRATED`` when there are not enough settled samples;
    the system never fabricates a calibration it cannot support.
    """

    raw: float = Field(ge=0, le=1)
    calibrated: float | None = Field(default=None, ge=0, le=1)
    status: CalibrationStatus = CalibrationStatus.UNCALIBRATED  # UNCALIBRATED | CALIBRATED
    n: int = 0
    calibration_group: str = "default"
