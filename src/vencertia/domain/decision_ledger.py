"""Decision ledger — DecisionRecord / DecisionOutcomeRecord (V-2).

These objects are persisted through the generic ``entities`` table (no new
migration) so all three backends (SQLite / PostgreSQL / InMemory) align for
free. Regret is only estimated when utility labels exist; v1.2 has no utility
labels, so ``regret_estimate`` is honestly ``None`` and the counterfactual
status is ``NOT_IDENTIFIABLE``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class CounterfactualStatus(str, Enum):
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    LOW_CONFIDENCE_ESTIMATE = "LOW_CONFIDENCE_ESTIMATE"
    ESTIMATED = "ESTIMATED"
    OBSERVED = "OBSERVED"


class DecisionRecord(VencertiaBaseModel):
    """One persisted row per decision, linking recommendation → action → outcome."""

    id: str  # DR_...
    decision_id: str
    project_id: str
    recommendation: str | None = None  # recommended_option_id
    action_taken: str | None = None  # the action actually adopted (backfilled on outcome)
    model_version: str | None = None  # policy_version or model_tag
    status: str = "RECOMMENDED"  # RECOMMENDED | ACTED | SETTLED
    abstain_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1


class DecisionOutcomeRecord(VencertiaBaseModel):
    """One row per recorded outcome, linked back to its DecisionRecord."""

    id: str  # OLR_...
    decision_record_id: str
    outcome_id: str | None = None
    regret_estimate: float | None = None  # no utility labels -> None (honest N/A)
    counterfactual_status: CounterfactualStatus = CounterfactualStatus.NOT_IDENTIFIABLE
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1


__all__ = ["CounterfactualStatus", "DecisionOutcomeRecord", "DecisionRecord"]
