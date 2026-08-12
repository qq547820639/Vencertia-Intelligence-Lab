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
        predictions = self.repo.list_predictions()
        settled = [
            p
            for p in predictions
            if p.resolution in ("TRUE", "FALSE")
            and (calibration_group == "default" or p.domain == calibration_group)
        ]
        n = len(settled)
        if n < self.min_samples:
            return CalibratedConfidence(
                raw=raw, calibrated=None, status="UNCALIBRATED", n=n, calibration_group=calibration_group
            )
        bins = self._bins_from_predictions(settled)
        calibrated = self._piecewise(raw, bins)
        return CalibratedConfidence(
            raw=raw,
            calibrated=calibrated,
            status="CALIBRATED",
            n=n,
            calibration_group=calibration_group,
        )

    @staticmethod
    def _bins_from_predictions(settled) -> list[dict]:
        """Equal-width bins with empirical rates (same bucketing as CalibrationEngine)."""
        bins: list[dict] = []
        n_bins = 10
        for i in range(n_bins):
            lo = i / n_bins
            hi = (i + 1) / n_bins
            bucket = [
                p
                for p in settled
                if lo <= p.predicted_probability < hi
                or (i == n_bins - 1 and p.predicted_probability == 1.0)
            ]
            if not bucket:
                continue
            conf = sum(x.predicted_probability for x in bucket) / len(bucket)
            rate = sum(1.0 for x in bucket if x.outcome) / len(bucket)
            bins.append({"lo": lo, "hi": hi, "mean_confidence": conf, "empirical_rate": rate})
        return bins

    @staticmethod
    def _piecewise(raw: float, bins: list[dict]) -> float:
        """Piecewise-linear map from mean_confidence to empirical_rate."""
        if not bins:
            return raw
        raw = max(0.0, min(1.0, raw))
        for idx, current in enumerate(bins):
            next_bin = bins[idx + 1] if idx + 1 < len(bins) else None
            lo = current["mean_confidence"]
            hi = next_bin["mean_confidence"] if next_bin else 1.0
            if lo <= raw <= hi:
                rate_lo = current["empirical_rate"]
                rate_hi = next_bin["empirical_rate"] if next_bin else rate_lo
                if hi == lo:
                    return round(rate_lo, 6)
                fraction = (raw - lo) / (hi - lo)
                return round(rate_lo + fraction * (rate_hi - rate_lo), 6)
        return round(bins[-1]["empirical_rate"], 6)
