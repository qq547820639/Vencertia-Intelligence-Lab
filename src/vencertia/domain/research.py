"""Research planning / tracing domain objects (ADR-011).

Research is planned as explicit questions and traced round by round so the
stopping rule has real signals to evaluate (marginal value / diversity /
coverage / delta / cost / duplicate rate / source quality).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import VencertiaBaseModel, utcnow


class ResearchQuestion(VencertiaBaseModel):
    """One falsifiable research question targeting decision-critical claims."""

    id: str  # RQ_...
    decision_id: str | None = None
    target_claim_ids: list[str] = Field(default_factory=list)
    question: str
    reason: str = ""
    expected_decision_impact: float = Field(ge=0, le=1, default=0.5)
    preferred_source_types: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    stop_condition: str = ""


class ResearchPlan(VencertiaBaseModel):
    """A deterministic research plan for one decision."""

    id: str  # RP_...
    decision_id: str
    questions: list[ResearchQuestion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    version: int = 1


class ResearchTrace(VencertiaBaseModel):
    """One round of research execution (persisted for audit + stopping signals)."""

    id: str  # RT_...
    decision_id: str
    question_id: str
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    query: str = ""
    queries_executed: int = 0
    results_retrieved: int = 0
    new_evidence_ids: list[str] = Field(default_factory=list)
    duplicate_dropped: int = 0
    stop_status: str = "RESEARCH_MORE"  # RESEARCH_MORE | SEARCH_EXHAUSTED | EXPERIMENT_REQUIRED
    stop_reason: str = ""
    provider: str = ""
    model: str = ""
    request_id: str = ""
    version: int = 1


class ResearchStopReport(VencertiaBaseModel):
    """Output of the ResearchStopRule with the full signal set."""

    status: str = "RESEARCH_MORE"
    reason: str = ""
    signals: dict = Field(default_factory=dict)
    per_question: list[dict] = Field(default_factory=list)
