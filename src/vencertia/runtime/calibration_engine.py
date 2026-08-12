"""CalibrationEngine — Brier / ECE / buckets / stratified profiles.

Only settled predictions (TRUE/FALSE) are counted. Resolution is irreversible;
the engine never rewrites an original probability (docs/calibration.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    CalibratedConfidence,
    CalibrationProfile,
    CalibrationScope,
    PredictionEntry,
    utcnow,
)
from vencertia.events.bus import EventBus
from vencertia.events.types import DomainEvent, EventType


@dataclass
class CalibrationInput:
    predictions: list[PredictionEntry]
    scope: CalibrationScope = CalibrationScope.ALL
    scope_key: str = "ALL"
    bins: int = 10


def _settled(predictions: list[PredictionEntry]) -> list[PredictionEntry]:
    return [p for p in predictions if p.resolution in ("TRUE", "FALSE")]


class CalibrationEngine:
    """Deterministic calibration metrics with stratification."""

    def __init__(self, settings: Settings | None = None, bus: EventBus | None = None) -> None:
        self.settings = settings or get_settings()
        self.bus = bus

    def report(self, inp: CalibrationInput) -> CalibrationProfile:
        done = _settled(inp.predictions)
        profile_id = "CAL_" + uuid4().hex
        if not done:
            return CalibrationProfile(
                id=profile_id,
                scope=inp.scope.value if hasattr(inp.scope, "value") else str(inp.scope),
                scope_key=inp.scope_key,
                n=0,
                bins=[],
            )

        n = len(done)
        outcomes = [1.0 if p.outcome else 0.0 for p in done]
        probs = [p.predicted_probability for p in done]
        brier = sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n

        bins = inp.bins if inp.bins > 0 else 10
        bucket_rows: list[dict] = []
        ece = 0.0
        for i in range(bins):
            lo = i / bins
            hi = (i + 1) / bins
            bucket = [
                (p, o)
                for p, o in zip(probs, outcomes)
                if lo <= p < hi or (i == bins - 1 and p == 1.0)
            ]
            if not bucket:
                continue
            conf = sum(x[0] for x in bucket) / len(bucket)
            rate = sum(x[1] for x in bucket) / len(bucket)
            ece += (len(bucket) / n) * abs(conf - rate)
            bucket_rows.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "n": len(bucket),
                    "mean_confidence": round(conf, 6),
                    "empirical_rate": round(rate, 6),
                    "gap": round(conf - rate, 6),
                }
            )

        return CalibrationProfile(
            id=profile_id,
            scope=inp.scope.value if hasattr(inp.scope, "value") else str(inp.scope),
            scope_key=inp.scope_key,
            n=n,
            brier_score=round(brier, 6),
            expected_calibration_error=round(ece, 6),
            mean_confidence=round(sum(probs) / n, 6),
            empirical_rate=round(sum(outcomes) / n, 6),
            bins=bucket_rows,
            updated_at=utcnow(),
        )

    def update(self, inp: CalibrationInput) -> CalibrationProfile:
        profile = self.report(inp)
        if self.bus is not None:
            self.bus.publish(
                DomainEvent(
                    event_type=EventType.CALIBRATION_UPDATED,
                    entity_type="calibration",
                    entity_id=profile.id,
                    payload={
                        "scope": profile.scope,
                        "scope_key": profile.scope_key,
                        "n": profile.n,
                        "brier_score": profile.brier_score,
                        "ece": profile.expected_calibration_error,
                    },
                )
            )
        return profile

    def update_all_scopes(self, predictions: list[PredictionEntry]) -> list[CalibrationProfile]:
        """Produce ALL / MODEL / DOMAIN / MODULE stratified profiles."""
        profiles = [
            self.update(CalibrationInput(predictions, CalibrationScope.ALL, "ALL", self.settings.ece_bins))
        ]
        seen_model: set[tuple[str, str]] = set()
        seen_domain: set[str] = set()
        seen_module: set[str] = set()
        for p in predictions:
            if p.resolution not in ("TRUE", "FALSE"):
                continue
            model_key = (p.model_tag, p.policy_version)
            if model_key not in seen_model:
                seen_model.add(model_key)
                subset = [
                    x for x in predictions if (x.model_tag, x.policy_version) == model_key
                ]
                profiles.append(
                    self.update(
                        CalibrationInput(
                            subset,
                            CalibrationScope.MODEL,
                            f"{p.model_tag}@{p.policy_version}",
                            self.settings.ece_bins,
                        )
                    )
                )
            if p.domain not in seen_domain:
                seen_domain.add(p.domain)
                subset = [x for x in predictions if x.domain == p.domain]
                profiles.append(
                    self.update(
                        CalibrationInput(
                            subset,
                            CalibrationScope.DOMAIN,
                            p.domain,
                            self.settings.ece_bins,
                        )
                    )
                )
            if p.module_tag not in seen_module:
                seen_module.add(p.module_tag)
                subset = [x for x in predictions if x.module_tag == p.module_tag]
                profiles.append(
                    self.update(
                        CalibrationInput(
                            subset,
                            CalibrationScope.MODULE,
                            p.module_tag,
                            self.settings.ece_bins,
                        )
                    )
                )
        return profiles

    def calibrate(
        self,
        raw: float,
        calibration_group: str = "default",
        predictions: list[PredictionEntry] | None = None,
        min_samples: int = 20,
    ) -> CalibratedConfidence:
        """Map a raw confidence to a calibrated value (v1.1).

        Uses settled predictions of the group (``domain == group`` for
        non-default groups; all settled for ``default``). With fewer than
        ``min_samples`` samples, returns ``UNCALIBRATED`` with calibrated=None
        — the system never fabricates calibration it cannot support.
        """
        raw = max(0.0, min(1.0, float(raw)))
        if predictions is None:
            return CalibratedConfidence(raw=raw, calibrated=None, status="UNCALIBRATED", n=0)
        settled = [
            p
            for p in predictions
            if p.resolution in ("TRUE", "FALSE")
            and (calibration_group == "default" or p.domain == calibration_group)
        ]
        n = len(settled)
        if n < min_samples:
            return CalibratedConfidence(
                raw=raw,
                calibrated=None,
                status="UNCALIBRATED",
                n=n,
                calibration_group=calibration_group,
            )
        bins = self._bins(settled)
        calibrated = self._map_piecewise(raw, bins)
        return CalibratedConfidence(
            raw=raw,
            calibrated=calibrated,
            status="CALIBRATED",
            n=n,
            calibration_group=calibration_group,
        )

    @staticmethod
    def _bins(settled: list[PredictionEntry]) -> list[dict]:
        n_bins = 10
        bins: list[dict] = []
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
    def _map_piecewise(raw: float, bins: list[dict]) -> float:
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
