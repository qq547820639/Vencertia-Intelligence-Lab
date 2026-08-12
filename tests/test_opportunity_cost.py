"""OpportunityCostEngine tests."""

from __future__ import annotations

from vencertia.domain import Belief, Decision, DecisionOption, Project
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.opportunity_cost import OpportunityCostEngine


def _project(pid, user="u1") -> Project:
    return Project(id=pid, user_id=user, name=pid)


def test_portfolio_opportunity_cost():
    repo = InMemoryRepository()
    repo.save_project(_project("PRJ_A"))
    repo.save_project(_project("PRJ_B"))
    repo.save_project(_project("PRJ_C"))
    for pid, belief_p in [("PRJ_A", 0.9), ("PRJ_B", 0.5), ("PRJ_C", 0.2)]:
        repo.save_belief(
            Belief(id=f"blf_{pid}", claim_id=f"CLM_{pid}", statement=pid, scope="PROJECT",
                   project_id=pid, posterior=belief_p, probability=belief_p,
                   alpha=10, beta=1, decision_relevant=True)
        )
        repo.save_decision(
            Decision(
                id=f"DEC_{pid}", decision_question=pid, objective_id="OBJ_1",
                project_id=pid,
                options=[
                    DecisionOption(id="go", label="go", kind="GO", base_utility=0.0,
                                   belief_coefficients={f"blf_{pid}": 1.0}),
                    DecisionOption(id="stop", label="stop", kind="KILL", base_utility=0.1,
                                   belief_coefficients={f"blf_{pid}": -0.2}),
                ],
                relevant_belief_ids=[f"blf_{pid}"],
            )
        )
    engine = OpportunityCostEngine(repo)
    portfolio = engine.portfolio("u1")
    assert len(portfolio.opportunities) == 3
    by_project = {o.project_id: o for o in portfolio.opportunities}
    # opportunity cost = expected value of best alternative
    assert by_project["PRJ_A"].opportunity_cost > 0
    assert by_project["PRJ_A"].priority == 1  # highest expected value


def test_portfolio_empty():
    repo = InMemoryRepository()
    engine = OpportunityCostEngine(repo)
    portfolio = engine.portfolio("u1")
    assert portfolio.opportunities == []
