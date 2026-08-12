"""OpportunityCostEngine — founder opportunity portfolio valuation [H2].

opportunity_cost(project) = expected value of the best alternative opportunity.
expected_value comes from the project's latest decision (best adjusted utility)
or falls back to an explicit value if the decision is absent.
"""

from __future__ import annotations

from vencertia.config import Settings, get_settings
from vencertia.domain import (
    Decision,
    FounderOpportunityPortfolio,
    Opportunity,
    Project,
    utcnow,
)
from vencertia.repositories.base import Repository
from vencertia.runtime.uncertainty_engine import compute_option_scores


class OpportunityCostEngine:
    """Deterministic portfolio opportunity-cost computation."""

    def __init__(self, repo: Repository, settings: Settings | None = None) -> None:
        self.repo = repo
        self.settings = settings or get_settings()

    def portfolio(self, user_id: str) -> FounderOpportunityPortfolio:
        projects = self.repo.list_projects(user_id)
        values: list[tuple[Project, float]] = []
        for project in projects:
            expected = self._expected_value(project)
            values.append((project, expected))

        values.sort(key=lambda item: item[1], reverse=True)
        opportunities: list[Opportunity] = []
        for index, (project, expected) in enumerate(values):
            best_alternative = max(
                (other for other_project, other in values if other_project.id != project.id),
                default=0.0,
            )
            option_value = 0.3 * expected
            opportunities.append(
                Opportunity(
                    project_id=project.id,
                    name=project.name,
                    expected_value=round(expected, 4),
                    option_value=round(option_value, 4),
                    opportunity_cost=round(best_alternative, 4),
                    priority=min(10, index + 1),
                    as_of=utcnow(),
                )
            )
        portfolio = FounderOpportunityPortfolio(
            user_id=user_id, opportunities=opportunities, updated_at=utcnow()
        )
        self.repo.save_portfolio(portfolio)
        return portfolio

    def _expected_value(self, project: Project) -> float:
        decisions = self.repo.list_decisions(project.id)
        if not decisions:
            return 0.0
        latest = max(decisions, key=lambda d: d.updated_at)
        return self._best_adjusted_utility(latest)

    def _best_adjusted_utility(self, decision: Decision) -> float:
        beliefs = self.repo.get_beliefs(decision.project_id)
        scores = compute_option_scores(decision, beliefs, self.settings.risk_aversion)
        if not scores:
            return 0.0
        return max(s.adjusted_utility for s in scores)
