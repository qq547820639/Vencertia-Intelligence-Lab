"""QA adversarial tests — Requirement 2: Decision/Experiment space separation.

ABSTAIN must simultaneously output a next_experiment; experiments must never
appear as decision options. The first test is adversarial: it uses a provider
whose compile returns NO experiments and asserts the invariant still holds
(the orchestrator must synthesize/guarantee a next experiment on ABSTAIN).
"""

from __future__ import annotations

from vencertia.domain import Belief, Decision, DecisionOption
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest
from vencertia.runtime.decision_engine import DecisionEngine, DecisionEngineInput


class NoExperimentProvider:
    """Compiles a decision but never proposes any experiments (lean LLM output)."""

    name = "no_experiment"

    def generate_structured(self, task: str, schema: dict, context: dict) -> dict:
        raw = MockProvider().generate_structured(task, schema, context)
        raw["experiments"] = []
        return raw


def test_abstain_requires_next_experiment_even_without_candidates() -> None:
    """HARD REQUIREMENT: ABSTAIN must always carry a next_experiment.

    Currently the orchestrator leaves next_experiment=None when the compiler
    returns no experiment candidates (repro: convergence SEARCH_EXHAUSTED).
    This is an invariant violation per requirement #2 / README "ABSTAIN 必带
    next_experiment" / ADR-007.
    """
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(repo=repo, bus=bus, model=NoExperimentProvider())
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_NOEXP",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert result.decision.status == "ABSTAIN"
    # --- the invariant under test ---
    assert result.next_experiment is not None, (
        "ABSTAIN returned without next_experiment: violates requirement #2 "
        "(ABSTAIN 必须同时输出 next_experiment)."
    )


def test_abstain_with_default_provider_emits_next_experiment() -> None:
    """With the default compiler, ABSTAIN carries the top-ranked experiment."""
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_EXP_OK",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert result.decision.status == "ABSTAIN"
    assert result.next_experiment is not None
    assert result.next_experiment.experiment.target_belief_ids  # targets critical beliefs


def test_experiments_never_appear_as_decision_options() -> None:
    """Experiments are information-acquisition actions, not resource options."""
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_SEP",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    stored_decision = orchestrator.repo.get_decision(result.decision_id)
    experiment_ids = (
        {result.next_experiment.experiment.id} if result.next_experiment is not None else set()
    )
    decision_option_ids = {o.id for o in stored_decision.options}
    assert experiment_ids.isdisjoint(decision_option_ids)


def test_abstain_recommended_option_is_none() -> None:
    """ABSTAIN must never recommend a resource-commitment option."""
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(repo=repo, bus=bus, model=MockProvider())
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_ABS",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    if result.decision.status == "ABSTAIN":
        assert result.decision.recommended_option_id is None


def test_experiment_propose_never_scores_experiments_as_options() -> None:
    """Even when experiments exist, the decision engine only scores decision options."""
    beliefs = [
        Belief(id="wtp", claim_id="CLM_wtp", statement="wtp", scope="PROJECT",
               project_id="PRJ_1", posterior=0.8, probability=0.8, alpha=8, beta=2,
               uncertainty=0.3, decision_relevant=True)
    ]
    decision = Decision(
        id="DEC_1", decision_question="q", objective_id="OBJ_1", project_id="PRJ_1",
        options=[DecisionOption(id="a", label="a"), DecisionOption(id="b", label="b")],
        relevant_belief_ids=["wtp"],
    )
    result = DecisionEngine().evaluate(DecisionEngineInput(decision=decision, beliefs=beliefs))
    option_ids = {s.option_id for s in result.option_scores}
    assert option_ids == {"a", "b"}
    assert "pilot" not in option_ids
