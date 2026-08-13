"""UtilityComponent / UtilityRelationType — non-linear utility relations (V-5).

``DecisionOption.utility_components`` is ``None`` by default, which routes
scoring through the original linear ``belief_coefficients`` path unchanged.
When present, hard constraints (AND_GATE/THRESHOLD/MINIMUM_REQUIRED) are
evaluated FIRST and can block an option before additive/multiplicative terms.
"""

from __future__ import annotations

from enum import Enum

from vencertia.domain.base import VencertiaBaseModel


class UtilityRelationType(str, Enum):
    ADDITIVE = "ADDITIVE"
    MULTIPLICATIVE = "MULTIPLICATIVE"
    THRESHOLD = "THRESHOLD"
    AND_GATE = "AND_GATE"
    OR_GATE = "OR_GATE"
    MINIMUM_REQUIRED = "MINIMUM_REQUIRED"
    INTERACTION = "INTERACTION"
    NONLINEAR = "NONLINEAR"
    UNKNOWN = "UNKNOWN"


class UtilityComponent(VencertiaBaseModel):
    """One contribution to an option's utility.

    ``threshold`` is used by THRESHOLD / AND_GATE / MINIMUM_REQUIRED relations.
    """

    belief_id: str
    relation_type: UtilityRelationType = UtilityRelationType.ADDITIVE
    coefficient: float = 1.0
    threshold: float | None = None


__all__ = ["UtilityComponent", "UtilityRelationType"]
