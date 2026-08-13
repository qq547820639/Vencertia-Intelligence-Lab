"""Model critique — ModelCritique / ModelCriticGate (V-3).

A ``ModelCritique`` is the structured, machine-readable counterpart to the
ChallengerCapability's counter-evidence. ``ModelCriticGate`` decides when a
critique is mandatory based on the decision's stakes class using a pure string
ordering (LOW=1 / MEDIUM=2 / HIGH=3) — it deliberately does NOT import
``StakesClass`` so Task C can compile and test independently of Task D.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class ModelRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CritiqueFindingType(str, Enum):
    MISSING_VARIABLE = "MISSING_VARIABLE"
    HIDDEN_DEPENDENCY = "HIDDEN_DEPENDENCY"
    REGIME_RISK = "REGIME_RISK"
    DOUBLE_COUNTING = "DOUBLE_COUNTING"
    TAIL_RISK = "TAIL_RISK"
    MODEL_MISSPECIFICATION = "MODEL_MISSPECIFICATION"


class ModelCritique(VencertiaBaseModel):
    """Structured findings from a model critic."""

    id: str  # MCR_...
    decision_id: str
    missing_variables: list[str] = Field(default_factory=list)
    hidden_dependencies: list[str] = Field(default_factory=list)
    regime_risks: list[str] = Field(default_factory=list)
    double_counting: list[str] = Field(default_factory=list)
    model_risk: ModelRisk = ModelRisk.LOW
    findings: list[CritiqueFindingType] = Field(default_factory=list)
    recommendation: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1


_STAKES_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


class ModelCriticGate:
    """Pure gate: does this stakes class require a mandatory model critic?"""

    @staticmethod
    def should_require(stakes_class: str | None, required: str = "HIGH") -> bool:
        """Return True when ``stakes_class`` reaches ``required`` (default HIGH).

        ``stakes_class is None`` -> False (no stakes information → no mandate).
        """
        if stakes_class is None:
            return False
        stakes_rank = _STAKES_ORDER.get(str(stakes_class).upper(), 0)
        required_rank = _STAKES_ORDER.get(str(required).upper(), 3)
        return stakes_rank >= required_rank


__all__ = ["CritiqueFindingType", "ModelCriticGate", "ModelCritique", "ModelRisk"]
