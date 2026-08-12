"""Decision trace / sensitivity domain objects (v1.1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class BeliefContribution(VencertiaBaseModel):
    """One belief's contribution to the expected utility decomposition."""

    belief_id: str
    claim_id: str
    contribution: float = 0.0
    direction: str = "NEUTRAL"  # SUPPORTS | CONTRADICTS | NEUTRAL


class DecisionTrace(VencertiaBaseModel):
    """Full expected-utility decomposition of one decision evaluation."""

    id: str  # DT_...
    decision_id: str
    option_utilities: list[dict] = Field(default_factory=list)
    belief_contributions: list[BeliefContribution] = Field(default_factory=list)
    penalties: dict = Field(default_factory=dict)
    margin: float = 0.0
    critical_uncertainty: float = 0.0
    computed_at: datetime = Field(default_factory=utcnow)
    version: int = 1


class FlipThreshold(VencertiaBaseModel):
    """A belief value at which the decision recommendation flips."""

    belief_id: str
    claim_id: str
    current_value: float
    threshold_value: float
    would_become: str = ""
    direction: str = "falls_below"  # falls_below | rises_above


class DecisionSensitivity(VencertiaBaseModel):
    """Robustness analysis: flip thresholds + STRONG/FRAGILE verdict."""

    id: str  # DS_...
    decision_id: str
    current_recommendation: str = ""
    flips: list[FlipThreshold] = Field(default_factory=list)
    robustness: str = "FRAGILE_DECISION"
    what_could_change_my_mind: list[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=utcnow)
    version: int = 1
