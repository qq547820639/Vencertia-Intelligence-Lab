"""QA adversarial tests — Requirement 6: Outcome re-updates Decision.

Full closed loop: record outcome -> belief drops -> decision re-evaluated ->
decision RESULT changes (GO flips to ABSTAIN after repeated failures).
"""

from __future__ import annotations

from vencertia.domain import (
    Action,
    Belief,
    Decision,
    DecisionOption,
    OutcomeType,
    Project,
    Scope,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockSearchProvider, MockRetrievalProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator


def _belief(project_id: str, bid: str, p: float, alpha: float, beta: float) -> Belief:
    mass = alpha + beta - 2.0
    maturity = 1.0 / (1.0 + mass / 6.0)
    unc = max(0.0, min(1.0, 4.0 * p * (1.0 - p) * (0.35 + 0.65 * maturity)))
    return Belief(
        id=bid, claim_id="CLM_" + bid, statement=bid, scope=Scope.PROJECT,
        project_id=project_id, posterior=p, probability=p, alpha=alpha, beta=beta,
        uncertainty=unc, confidence=1.0 - unc, decision_relevant=True,
    )


def _flip_fixture() -> tuple[SolveOrchestrator, InMemoryRepository, str]:
    """GO decision with margin just above threshold; repeated failures flip to ABSTAIN."""
    repo = InMemoryRepository()
    repo.save_project(Project(id="PRJ_FLIP", user_id="u1", name="p"))
    repo.save_belief(_belief("PRJ_FLIP", "wtp", 0.75, 6.0, 2.0))
    repo.save_belief(_belief("PRJ_FLIP", "problem", 0.60, 6.0, 4.0))
    decision = Decision(
        id="DEC_FLIP", decision_question="commit?", objective_id="OBJ_1", project_id="PRJ_FLIP",
        options=[
            DecisionOption(id="commit", label="Commit", kind="GO", base_utility=0.30,
                           belief_coefficients={"wtp": 0.4, "problem": 0.0}),
            DecisionOption(id="hold", label="Hold", kind="HOLD", base_utility=0.28,
                           belief_coefficients={"wtp": 0.2, "problem": 0.0}),
        ],
        relevant_belief_ids=["wtp", "problem"], status="DRAFT",
    )
    repo.save_decision(decision)
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo, bus=bus, model=MockProvider(),
        search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
    )
    return orchestrator, repo, "DEC_FLIP"


def test_outcome_belief_decreases() -> None:
    orchestrator, repo, decision_id = _flip_fixture()
    repo.save_action(
        Action(id="ACT_0", project_id="PRJ_FLIP", kind="EXPERIMENT", description="pilot",
               decision_id=decision_id, experiment_id="EXP_1")
    )
    before = repo.get_belief("wtp").probability
    recorded = orchestrator.record_outcome(
        "ACT_0", "0 paid", quantitative={"wtp": 0.0}, outcome_type=OutcomeType.FAILURE
    )
    after = repo.get_belief("wtp").probability
    assert after < before
    assert recorded.outcome.outcome_type == "FAILURE"


def test_outcome_reevaluates_decision() -> None:
    orchestrator, repo, decision_id = _flip_fixture()
    initial, _ = orchestrator.evaluate_decision(decision_id)
    assert initial.status == "GO"  # precondition: strong case commits
    before_version = repo.get_decision(decision_id).version

    repo.save_action(
        Action(id="ACT_R", project_id="PRJ_FLIP", kind="EXPERIMENT", description="pilot",
               decision_id=decision_id, experiment_id="EXP_1")
    )
    recorded = orchestrator.record_outcome(
        "ACT_R", "0 paid", quantitative={"wtp": 0.0}, outcome_type=OutcomeType.FAILURE
    )
    assert recorded.decision_update is not None
    stored = repo.get_decision(decision_id)
    assert stored.version >= before_version + 1  # decision was re-written


def test_evaluate_decision_marks_status_evaluated() -> None:
    """evaluate_decision must persist status=EVALUATED on the decision.

    Reproduces a source inconsistency: solve() sets status='EVALUATED' but
    evaluate_decision() (used by the closed loop and /v1/decisions/evaluate)
    does not — a DRAFT decision stays DRAFT after evaluation.
    """
    orchestrator, repo, decision_id = _flip_fixture()
    assert repo.get_decision(decision_id).status == "DRAFT"
    result, _ = orchestrator.evaluate_decision(decision_id)
    assert result.status == "GO"
    stored = repo.get_decision(decision_id)
    assert stored.status == "EVALUATED", (
        "evaluate_decision did not persist status=EVALUATED (status stayed "
        f"{stored.status!r})"
    )


def test_outcome_changes_decision_result_go_to_abstain() -> None:
    """HARD REQUIREMENT: result must CHANGE after enough negative outcomes."""
    orchestrator, repo, decision_id = _flip_fixture()
    initial, _ = orchestrator.evaluate_decision(decision_id)
    assert initial.status == "GO"

    flipped_status = None
    for i in range(8):
        aid = f"ACT_F{i}"
        repo.save_action(
            Action(id=aid, project_id="PRJ_FLIP", kind="EXPERIMENT", description="pilot",
                   decision_id=decision_id, experiment_id="EXP_1")
        )
        recorded = orchestrator.record_outcome(
            aid, f"failure {i}", quantitative={"wtp": 0.0}, outcome_type=OutcomeType.FAILURE
        )
        if recorded.decision_update is not None and recorded.decision_update.status != initial.status:
            flipped_status = recorded.decision_update.status
            break

    assert flipped_status is not None, "decision result never changed after outcomes"
    assert flipped_status == "ABSTAIN"
    # Belief clearly degraded from 0.75 toward 0.
    assert repo.get_belief("wtp").probability < 0.5
