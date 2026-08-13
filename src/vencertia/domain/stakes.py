"""StakesProfile / StakesClass — decision stakes classification (V-4).

``StakesClass`` drives the three-band ABSTAIN thresholds
(``Settings.stakes_thresholds``). The default is ``MEDIUM`` so that a decision
without explicit stakes reproduces v1.1.2's single global threshold band
exactly (minimum_margin=0.08 / max_critical_uncertainty=0.45).
"""

from __future__ import annotations

from enum import Enum

from vencertia.domain.base import VencertiaBaseModel


class StakesClass(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StakesProfile(VencertiaBaseModel):
    """Structured description of what is at stake for a decision.

    All fields are optional/optional-with-default; ``stakes_class`` is the
    derived classification used by the DecisionEngine to select the threshold
    band. It is stored as a plain string via ``use_enum_values`` so old JSON
    round-trips unchanged.
    """

    financial_downside: float = 0.0
    reversibility: float = 1.0  # 1 = fully reversible
    time_to_recover: float = 0.0  # months
    legal_exposure: float = 0.0
    optionality: float = 1.0
    risk_tolerance: float = 0.5
    deadline_pressure: float = 0.0
    stakes_class: StakesClass = StakesClass.MEDIUM


__all__ = ["StakesClass", "StakesProfile"]
