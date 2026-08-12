"""ResearchPlanner — deterministic research-question generation (ADR-011).

Sorts critical uncertainties by impact and generates one ResearchQuestion per
top-k uncertainty. The mock provider can supply richer question templates; the
deterministic baseline is always the fallback.
"""

from __future__ import annotations

from uuid import uuid4

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Belief,
    CriticalUncertainty,
    Decision,
    ResearchPlan,
    ResearchQuestion,
    utcnow,
)
from vencertia.repositories.base import Repository


class ResearchPlanner:
    """Deterministic baseline: impact-sorted top-k research questions."""

    def __init__(
        self,
        model=None,
        settings: Settings | None = None,
        repo: Repository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = model
        self.repo = repo

    def plan(
        self,
        decision: Decision,
        beliefs: list[Belief],
        criticals: list[CriticalUncertainty],
        context=None,
    ) -> ResearchPlan:
        bm = {b.id: b for b in beliefs}
        claim_by_belief = {b.id: b.claim_id for b in beliefs}
        sorted_criticals = sorted(criticals, key=lambda c: c.impact, reverse=True)[
            : self.settings.research_max_questions
        ]
        questions: list[ResearchQuestion] = []
        for critical in sorted_criticals:
            belief = bm.get(critical.belief_id)
            statement = belief.statement if belief else critical.statement
            target_claims = [claim_by_belief.get(critical.belief_id, "")] if critical.belief_id else []
            target_claims = [c for c in target_claims if c]
            questions.append(
                ResearchQuestion(
                    id="RQ_" + uuid4().hex,
                    decision_id=decision.id,
                    target_claim_ids=target_claims,
                    question=f"What is the best available evidence on: {statement}?",
                    reason=(
                        f"Critical uncertainty impact={critical.impact:.3f}; "
                        f"uncertainty={critical.uncertainty:.3f}"
                    ),
                    expected_decision_impact=round(min(1.0, critical.impact), 6),
                    preferred_source_types=[
                        "OFFICIAL_DATA",
                        "PRIMARY_RESEARCH",
                        "REVIEWED_EXTERNAL_RESEARCH",
                    ],
                    search_queries=[
                        f"{statement} evidence",
                        f"{statement} data",
                    ],
                    stop_condition="3 independent sources agree or belief delta < 0.02",
                )
            )
        return ResearchPlan(
            id="RP_" + uuid4().hex,
            decision_id=decision.id,
            questions=questions,
            created_at=utcnow(),
        )
