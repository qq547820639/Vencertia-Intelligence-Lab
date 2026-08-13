"""v1.2 T3 critic-gate solve wiring acceptance tests."""

from __future__ import annotations

from vencertia.capabilities import ChallengerCapability
from vencertia.domain import (
    Belief,
    ConvergenceReport,
    Decision,
    DecisionOption,
    DecisionResult,
    ModelCritique,
    StakesProfile,
)
from vencertia.domain.context import ContextBundle
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import (
    SolveOrchestrator,
    SolveRequest,
    SolveResultV11,
)


def _orchestrator() -> SolveOrchestrator:
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    return SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
    )


def _decision(stakes_class: str = "HIGH") -> Decision:
    return Decision(
        id="DEC_1",
        decision_question="q",
        objective_id="OBJ_1",
        project_id="PRJ_1",
        options=[
            DecisionOption(id="a", label="a", base_utility=0.1),
            DecisionOption(id="b", label="b", base_utility=0.0),
        ],
        stakes_class=stakes_class,
    )


def _context() -> ContextBundle:
    return ContextBundle(
        user_id="u1",
        critical_assumptions=[
            Belief(
                id="wtp",
                claim_id="CLM_WTP",
                statement="wtp",
                scope="PROJECT",
                project_id="PRJ_1",
            )
        ],
    )


# --- field default ---------------------------------------------------------------


def test_model_critique_field_defaults_to_none():
    result = SolveResultV11(
        decision=DecisionResult(
            decision_id="DEC_1",
            status="HOLD",
            recommended_option_id=None,
            confidence=0.5,
            decision_margin=0.0,
        ),
        decision_id="DEC_1",
        convergence=ConvergenceReport(decision_id="DEC_1"),
    )
    assert result.model_critique is None
    assert result.action_state is None
    assert result.advanced_view is None


# --- gate trigger / non-trigger ----------------------------------------------------


def test_gate_triggers_critic_for_high_stakes():
    orchestrator = _orchestrator()
    critique = orchestrator._run_model_critic(_decision("HIGH"), _context())
    assert isinstance(critique, ModelCritique)
    assert critique.model_risk in ("LOW", "MEDIUM", "HIGH")
    assert "MISSING_VARIABLE" in critique.findings
    assert "DOUBLE_COUNTING" in critique.findings


def test_gate_skips_critic_for_medium_stakes():
    orchestrator = _orchestrator()
    assert orchestrator._run_model_critic(_decision("MEDIUM"), _context()) is None


# --- degrade gracefully ---------------------------------------------------------------


def test_critic_failure_degrades_and_solve_proceeds(monkeypatch):
    orchestrator = _orchestrator()

    def _boom(task: str, context) -> None:
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(ChallengerCapability, "run", _boom)
    assert orchestrator._run_model_critic(_decision("HIGH"), _context()) is None

    # solve() with HIGH stakes must still return a valid result (never blocks).
    original_compile = orchestrator._compile

    def _high_stakes(request, project, context):
        compiled = original_compile(request, project, context)
        compiled.decision.stakes_class = "HIGH"
        compiled.decision.stakes = StakesProfile(stakes_class="HIGH")
        return compiled

    monkeypatch.setattr(orchestrator, "_compile", _high_stakes)
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_DEG",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert isinstance(result, SolveResultV11)
    assert result.model_critique is None  # critic failed → degraded
    assert result.decision.status in ("GO", "ABSTAIN", "HOLD", "PIVOT", "KILL", "SELECT_OPTION")


# --- solve integration ---------------------------------------------------------------


def test_solve_high_stakes_attaches_model_critique(monkeypatch):
    orchestrator = _orchestrator()
    original_compile = orchestrator._compile

    def _high_stakes(request, project, context):
        compiled = original_compile(request, project, context)
        compiled.decision.stakes_class = "HIGH"
        compiled.decision.stakes = StakesProfile(stakes_class="HIGH")
        return compiled

    monkeypatch.setattr(orchestrator, "_compile", _high_stakes)
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_HIGH",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert isinstance(result.model_critique, ModelCritique)
    assert result.model_critique.model_risk in ("LOW", "MEDIUM", "HIGH")


def test_solve_default_stakes_has_no_model_critique():
    orchestrator = _orchestrator()
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_MED",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert result.model_critique is None
