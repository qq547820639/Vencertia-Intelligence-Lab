"""ConfidenceCalibrator — raw→calibrated confidence with UNCALIBRATED honesty.

When there are fewer than ``min_samples`` settled predictions in a group, the
calibrator returns ``status=UNCALIBRATED`` with ``calibrated=None`` — it never
fabricates a calibration it cannot support (v1.1).
"""

from __future__ import annotations

from vencertia.config import Settings, get_settings
from vencertia.domain import CalibratedConfidence
from vencertia.repositories.base import Repository
from vencertia.runtime.calibration_engine import CalibrationEngine


class ConfidenceCalibrator:
    """Applies a piecewise-linear empirical calibration map from profile bins."""

    def __init__(
        self,
        calibration_engine: CalibrationEngine | None = None,
        repo: Repository | None = None,
        min_samples: int = 20,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.calibration_engine = calibration_engine or CalibrationEngine(self.settings)
        self.repo = repo
        self.min_samples = min_samples

    def calibrate(self, raw: float, calibration_group: str = "default") -> CalibratedConfidence:
        if self.repo is None:
            return CalibratedConfidence(raw=raw, calibrated=None, status="UNCALIBRATED", n=0)
        return self.calibration_engine.calibrate(
            raw,
            calibration_group,
            predictions=self.repo.list_predictions(),
            min_samples=self.min_samples,
        )
