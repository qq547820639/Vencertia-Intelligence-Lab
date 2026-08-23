"""v1.2 T3 critic-gate solve wiring acceptance tests.

v2.0.1 (product ruling): a canned/template critique must never be rendered as
user-visible "模型自检". The legacy ``ChallengerCapability`` emits fixed
strings and is therefore NOT wired into the solve path anymore; the critic
only runs when a real critique provider is explicitly injected.
"""

from __future__ import annotations

import json

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import (
    Belief,
    ConvergenceReport,
    CritiqueFindingType,
    Decision,
    DecisionOption,
    DecisionResult,
    ModelCritique,
    ModelRisk,
    StakesProfile,
)
from vencertia.domain.context import ContextBundle
from vencertia.events.bus import EventBus
from vencertia.presentation import solve_summary
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import (
    SolveOrchestrator,
    SolveRequest,
    SolveResultV11,
)


class _StubCritic:
    """Stand-in for a REAL critique provider (exercises the wiring only).

    Builds its critique from the actual decision/context instead of returning
    fixed strings, which is what separates a provider from a template.
    """

    name = "stub-critic"

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        decision_id = context.latest_decisions[0].id if context.latest_decisions else "UNKNOWN"
        claim_ids = [b.claim_id for b in context.critical_assumptions]
        critique = ModelCritique(
            id="MCR_STUB",
            decision_id=decision_id,
            missing_variables=[f"unexamined assumption: {cid}" for cid in claim_ids],
            findings=[CritiqueFindingType.MISSING_VARIABLE],
            model_risk=ModelRisk.MEDIUM,
            recommendation=f"Re-examine {len(claim_ids)} critical assumption(s).",
        )
        return CapabilityResult(evidence=[], critique=critique, notes=[])


class _FailingCritic:
    name = "failing-critic"

    def run(self, task: str, context: ContextBundle) -> None:
        raise RuntimeError("llm unavailable")


def _orchestrator(critic=None) -> SolveOrchestrator:
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    return SolveOrchestrator(
        repo=repo,
        bus=bus,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
        critic=critic,
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


def _high_stakes_patch(orchestrator, monkeypatch):
    original_compile = orchestrator._compile

    def _high_stakes(request, project, context):
        compiled = original_compile(request, project, context)
        compiled.decision.stakes_class = "HIGH"
        compiled.decision.stakes = StakesProfile(stakes_class="HIGH")
        return compiled

    monkeypatch.setattr(orchestrator, "_compile", _high_stakes)


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


def test_gate_triggers_critic_for_high_stakes_with_real_provider():
    orchestrator = _orchestrator(critic=_StubCritic())
    critique = orchestrator._run_model_critic(_decision("HIGH"), _context())
    assert isinstance(critique, ModelCritique)
    assert critique.model_risk in ("LOW", "MEDIUM", "HIGH")
    assert "MISSING_VARIABLE" in critique.findings


def test_gate_skips_critic_for_medium_stakes():
    orchestrator = _orchestrator(critic=_StubCritic())
    assert orchestrator._run_model_critic(_decision("MEDIUM"), _context()) is None


def test_high_stakes_without_critic_provider_returns_none():
    """v2.0.1: no canned fallback — no provider means NO critique."""
    orchestrator = _orchestrator()  # no critic wired
    assert orchestrator._run_model_critic(_decision("HIGH"), _context()) is None


# --- degrade gracefully ---------------------------------------------------------------


def test_critic_failure_degrades_and_solve_proceeds(monkeypatch):
    orchestrator = _orchestrator(critic=_FailingCritic())
    assert orchestrator._run_model_critic(_decision("HIGH"), _context()) is None

    # solve() with HIGH stakes must still return a valid result (never blocks).
    _high_stakes_patch(orchestrator, monkeypatch)
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
    orchestrator = _orchestrator(critic=_StubCritic())
    _high_stakes_patch(orchestrator, monkeypatch)
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
    orchestrator = _orchestrator(critic=_StubCritic())
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_MED",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert result.model_critique is None


# --- v2.0.1 regression: no canned critique in the product path -------------------

# Fixed strings emitted by the legacy ChallengerCapability template.
_CANNED_STRINGS = [
    "willingness-to-pay (interviews may overstate it)",
    "willingness-to-pay and adoption risk may overlap",
    "Validate willingness-to-pay with real payment evidence.",
    "Challenger capability (mock)",
]


def test_solve_high_stakes_without_provider_emits_no_canned_critique(monkeypatch):
    orchestrator = _orchestrator()  # no critic wired — the product default
    _high_stakes_patch(orchestrator, monkeypatch)
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_NOCAN",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert result.model_critique is None
    rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    rendered += json.dumps(solve_summary(result), ensure_ascii=False)
    for canned in _CANNED_STRINGS:
        assert canned not in rendered
    summary = solve_summary(result)
    assert summary["model_critique"]["available"] is False
    assert "不可用" in summary["model_critique"]["note"]
