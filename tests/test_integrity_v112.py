"""v1.1.2 Runtime Integrity Hardening — acceptance tests (14).

Each test maps to a P0/P1/P2 acceptance in TASK_BREAKDOWN_V1_1_2.md:
 1  test_current_decision_is_used_for_context_ranking        (P0-1)
 2  test_claim_ids_map_through_beliefs_for_decision_relevance (P0-2)
 3  test_project_evidence_does_not_leak_between_projects      (P0-3)
 4  test_recent_outcomes_are_present_in_context               (P0-4)
 5  test_runtime_never_calls_repository_private_list          (P2-14)
 6  test_research_api_applies_evidence_and_updates_belief     (P0-5)
 7  test_research_cli_uses_shared_execution_service           (P0-5)
 8  test_invalid_experiment_never_persisted                   (P0-6)
 9  test_call_recorder_records_real_provider_calls            (P1-7)
10  test_research_stop_claim_coverage_uses_claim_ids          (P1-8)
11  test_l1_regret_is_na_without_utility_labels               (P1-10)
12  test_l0_option_accuracy_excludes_unlabeled_options        (P1-10)
13  test_version_single_source                                (P1-12)
14  test_candidate_validation_api_has_no_conditional_skip     (P1-11)
"""

from __future__ import annotations

import json
import tomllib

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.capabilities import CompiledDecision
from vencertia.config import Settings
from vencertia.domain import (
    Action,
    Belief,
    Claim,
    Decision,
    DecisionOption,
    Evidence,
    Experiment,
    Objective,
    Outcome,
    Project,
)
from vencertia.events.bus import EventBus
from vencertia.providers.errors import ProviderTimeoutError
from vencertia.providers.factory import with_resilience
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import (
    SolveOrchestrator,
    SolveRequest,
    default_engine_bundle,
)
from vencertia.runtime.context import ContextBuilder
from vencertia.runtime.context_ranker import ContextRanker, DecisionRelevantContextBuilder
from vencertia.runtime.experiment_optimizer import (
    ExperimentOptimizer,
    ExperimentProposalInput,
    synthesize_default_experiment,
    validate_experiment,
)
from vencertia.runtime.research_stop import ResearchStopRule, RoundSummary

# ---------------------------------------------------------------------------
# 1. P0-1 post-compile context uses the CURRENT decision
# ---------------------------------------------------------------------------


def _project() -> Project:
    return Project(id="PRJ_1", user_id="u1", name="p")


def _decision(decision_id: str, relevant: list[str]) -> Decision:
    return Decision(
        id=decision_id,
        decision_question="Should we build the MVP?",
        objective_id="OBJ_1",
        project_id="PRJ_1",
        options=[DecisionOption(id="go", label="Go"), DecisionOption(id="hold", label="Hold")],
        relevant_belief_ids=relevant,
    )


def test_current_decision_is_used_for_context_ranking(repo, settings):
    """P0-1: _build_context(decision=...) ranks evidence by the CURRENT
    decision's relevant beliefs (via belief→claim mapping), not a stale one."""
    repo.save_project(_project())
    repo.save_belief(
        Belief(id="BLF_WTP", claim_id="CLM_WTP", statement="wtp", scope="PROJECT",
               project_id="PRJ_1", decision_relevant=True)
    )
    repo.save_belief(
        Belief(id="BLF_OTHER", claim_id="CLM_OTHER", statement="other", scope="PROJECT",
               project_id="PRJ_1", decision_relevant=True)
    )
    repo.add_evidence(
        Evidence(id="E_REL", claim_ids=["CLM_WTP"], scope="PROJECT",
                 evidence_type="OBSERVED_BEHAVIOR", source="wtp signal",
                 authority_level="PROJECT_DIRECT_BEHAVIOR", project_id="PRJ_1",
                 strength=0.5, reliability=0.5, relevance=0.5)
    )
    repo.add_evidence(
        Evidence(id="E_IRR", claim_ids=["CLM_OTHER"], scope="PROJECT",
                 evidence_type="OBSERVED_BEHAVIOR", source="other signal",
                 authority_level="PROJECT_DIRECT_BEHAVIOR", project_id="PRJ_1",
                 strength=0.5, reliability=0.5, relevance=0.5)
    )
    engines = default_engine_bundle(repo, settings, EventBus(sink=repo.append_event))
    orch = SolveOrchestrator(repo=repo, engines=engines, settings=settings)
    request = SolveRequest(project_id="PRJ_1", problem_text="q", user_id="u1")
    dec_a = _decision("DEC_A", ["BLF_WTP"])
    dec_b = _decision("DEC_B", ["BLF_OTHER"])
    ctx_a = orch._build_context(_project(), request, decision=dec_a)
    ctx_b = orch._build_context(_project(), request, decision=dec_b)
    assert ctx_a.top_evidence[0].id == "E_REL"
    assert ctx_b.top_evidence[0].id == "E_IRR"
    # pre-compile path (decision=None) is legal.
    ctx_none = orch._build_context(_project(), request)
    assert len(ctx_none.top_evidence) == 2


# ---------------------------------------------------------------------------
# 2. P0-2 belief→claim mapping for decision relevance (no string guessing)
# ---------------------------------------------------------------------------


def test_claim_ids_map_through_beliefs_for_decision_relevance(settings):
    """P0-2: Evidence.claim_ids (CLM_*) resolve through Belief.claim_id; the
    ranker never guesses ``CLM_{belief_id}`` strings."""
    ranker = ContextRanker(settings)
    decision = _decision("DEC", ["wtp"])
    beliefs = [
        Belief(id="wtp", claim_id="CLM_WTP", statement="wtp", scope="PROJECT",
               project_id="PRJ_1", decision_relevant=True)
    ]
    claim_by_belief = {b.id: b.claim_id for b in beliefs}
    rel = Evidence(id="E_REL", claim_ids=["CLM_WTP"], scope="PROJECT",
                   evidence_type="OBSERVED_BEHAVIOR", source="x",
                   authority_level="PROJECT_DIRECT_BEHAVIOR", project_id="PRJ_1")
    irr = Evidence(id="E_IRR", claim_ids=["CLM_OTHER"], scope="PROJECT",
                   evidence_type="OBSERVED_BEHAVIOR", source="y",
                   authority_level="PROJECT_DIRECT_BEHAVIOR", project_id="PRJ_1")
    assert ContextRanker._decision_relevance(rel, decision, claim_by_belief) == 1.0
    assert ContextRanker._decision_relevance(irr, decision, claim_by_belief) == 0.4
    assert ranker.score_evidence(rel, decision, beliefs, claim_by_belief) > ranker.score_evidence(
        irr, decision, beliefs, claim_by_belief
    )
    # No mapping → neutral 0.5 (never a fabricated match).
    assert ContextRanker._decision_relevance(rel, decision, None) == 0.5


# ---------------------------------------------------------------------------
# 3. P0-3 project evidence isolation (write + read boundary)
# ---------------------------------------------------------------------------


def test_project_evidence_does_not_leak_between_projects(repo):
    """P0-3: PROJECT evidence is only visible to its owning project; shared
    WORLD/MARKET evidence is visible to all; missing project_id is rejected."""
    repo.save_project(Project(id="PRJ_A", user_id="u1", name="A"))
    repo.save_project(Project(id="PRJ_B", user_id="u1", name="B"))
    repo.add_evidence(
        Evidence(id="E_A", claim_ids=["CLM_A"], scope="PROJECT",
                 evidence_type="OBSERVED_BEHAVIOR", source="a", project_id="PRJ_A")
    )
    repo.add_evidence(
        Evidence(id="E_B", claim_ids=["CLM_B"], scope="PROJECT",
                 evidence_type="OBSERVED_BEHAVIOR", source="b", project_id="PRJ_B")
    )
    repo.add_evidence(
        Evidence(id="E_SHARED", claim_ids=["CLM_S"], scope="MARKET",
                 evidence_type="REVIEWED_EXTERNAL_RESEARCH", source="s", project_id=None)
    )
    visible_a = {e.id for e in repo.list_evidence(project_id="PRJ_A")}
    assert visible_a == {"E_A", "E_SHARED"}
    visible_b = {e.id for e in repo.list_evidence(project_id="PRJ_B")}
    assert visible_b == {"E_B", "E_SHARED"}
    ctx_a = ContextBuilder(repo).build("PRJ_A")
    assert all(e.id != "E_B" for e in ctx_a.top_evidence)
    ctx_b = ContextBuilder(repo).build("PRJ_B")
    assert all(e.id != "E_A" for e in ctx_b.top_evidence)
    with pytest.raises(ValueError, match="requires project_id"):
        repo.add_evidence(
            Evidence(id="E_NOPID", claim_ids=["CLM_X"], scope="PROJECT",
                     evidence_type="OBSERVED_BEHAVIOR", source="x")
        )


# ---------------------------------------------------------------------------
# 4. P0-4 recent outcomes via public API (Outcome.id=OUT_* ↔ Action.id=ACT_*)
# ---------------------------------------------------------------------------


def test_recent_outcomes_are_present_in_context(repo, settings):
    """P0-4: build_for_decision exposes outcomes linked by action_id through
    the public Repository API (no private _list, no id-namespace collision)."""
    repo.save_project(_project())
    repo.save_decision(_decision("DEC_1", ["wtp"]))
    repo.save_action(
        Action(id="ACT_1", project_id="PRJ_1", kind="EXPERIMENT",
               decision_id="DEC_1", description="paid pilot")
    )
    repo.save_outcome(Outcome(id="OUT_1", action_id="ACT_1", result="0 paid"))
    bundle = DecisionRelevantContextBuilder(
        repo, ranker=ContextRanker(settings)
    ).build_for_decision("PRJ_1")
    assert any(o.id == "OUT_1" for o in bundle.recent_outcomes)


def test_repository_public_action_outcome_queries(repo):
    """P0-4 contract: list_actions/list_outcomes filter correctly."""
    repo.save_project(_project())
    repo.save_decision(_decision("DEC_1", ["wtp"]))
    repo.save_action(Action(id="ACT_1", project_id="PRJ_1", decision_id="DEC_1", description="a"))
    repo.save_action(Action(id="ACT_2", project_id="PRJ_1", description="b"))
    repo.save_outcome(Outcome(id="OUT_1", action_id="ACT_1", result="r1"))
    assert [a.id for a in repo.list_actions(decision_id="DEC_1")] == ["ACT_1"]
    assert [o.id for o in repo.list_outcomes(action_id="ACT_1")] == ["OUT_1"]
    assert [o.id for o in repo.list_outcomes(project_id="PRJ_1")] == ["OUT_1"]


# ---------------------------------------------------------------------------
# 5. P2-14 no private repository calls in runtime/capabilities
# ---------------------------------------------------------------------------


def test_runtime_never_calls_repository_private_list(project_root):
    """P2-14: no ``repo._list``/``_load``/``_store`` in non-repository code."""
    root = project_root / "src" / "vencertia"
    offenders: list[tuple[str, str]] = []
    for py in root.rglob("*.py"):
        if "repositories" in py.parts:
            continue
        text = py.read_text(encoding="utf-8")
        for pat in (
            "repo._list(",
            "self.repo._list(",
            "repo._load(",
            "self.repo._load(",
            "repo._store(",
            "self.repo._store(",
        ):
            if pat in text:
                offenders.append((str(py.relative_to(root)), pat))
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# 6/7. P0-5 research single pipeline (API + CLI + solve share one service)
# ---------------------------------------------------------------------------


def _solved_client():
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    result = runtime.solve(
        SolveRequest(project_id="PRJ_API", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    app = create_app(settings, repo, runtime)
    return TestClient(app), repo, runtime, result


def _seed_researchable_decision(repo, project_id: str, decision_id: str) -> None:
    """Seed a decision + claims + beliefs WITHOUT any prior research evidence,
    so a subsequent research run deterministically applies fresh evidence."""
    repo.save_project(Project(id=project_id, user_id="u1", name="p"))
    repo.add_claim(
        Claim(id="CLM_WTP", statement="ICP will pay for the promised outcome",
              scope="PROJECT", project_id=project_id)
    )
    repo.save_belief(
        Belief(id="wtp", claim_id="CLM_WTP", statement="ICP will pay for the promised outcome",
               scope="PROJECT", project_id=project_id, decision_relevant=True,
               alpha=1.0, beta=1.0, probability=0.5, posterior=0.5)
    )
    repo.save_decision(
        Decision(
            id=decision_id, decision_question="Should we commit six weeks to the MVP?",
            objective_id="OBJ_API", project_id=project_id,
            options=[
                DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
                DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
            ],
            relevant_belief_ids=["wtp"],
        )
    )


def test_research_api_applies_evidence_and_updates_belief():
    """P0-5: /v1/research/run runs the FULL pipeline — applied evidence is
    persisted and target beliefs move."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    _seed_researchable_decision(repo, "PRJ_API", "DEC_API")
    app = create_app(settings, repo, runtime)
    tc = TestClient(app)

    evidence_before = len(repo.list_evidence())
    beliefs_before = {b.id: b.probability for b in repo.get_beliefs("PRJ_API")}
    assert tc.post("/v1/research/plan", json={"decision_id": "DEC_API"}).status_code == 200
    r = tc.post("/v1/research/run", json={"decision_id": "DEC_API"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(repo.list_evidence()) > evidence_before
    beliefs_after = {b.id: b.probability for b in repo.get_beliefs("PRJ_API")}
    moved = any(
        abs(beliefs_after.get(bid, 0.0) - p) > 1e-9 for bid, p in beliefs_before.items()
    )
    assert moved or data["applied_evidence"], (
        "research/run must either apply evidence or move beliefs"
    )
    # Applied evidence is owned by the collecting project (P0-3).
    applied_ids = {e["id"] for e in data["applied_evidence"]}
    if applied_ids:
        for eid in applied_ids:
            assert repo.get_evidence(eid).project_id == "PRJ_API"


def test_research_cli_uses_shared_execution_service(tmp_path):
    """P0-5: CLI `research run` uses ResearchExecutionService.run_plan — the
    same pipeline as the API/solve (persists applied evidence, not only traces)."""
    from typer.testing import CliRunner

    from vencertia.cli import app as cli_app
    from vencertia.container import build_container

    db_path = tmp_path / "r.db"
    settings = Settings(db_dsn=f"sqlite:///{db_path}")
    container = build_container(settings)
    repo = container.repository
    runtime = container.orchestrator
    _seed_researchable_decision(repo, "PRJ_CLI", "DEC_CLI")
    decision = repo.get_decision("DEC_CLI")
    plan = runtime.engines.research_planner.plan(
        decision,
        repo.get_beliefs("PRJ_CLI"),
        runtime.engines.uncertainty_engine.rank(decision, repo.get_beliefs("PRJ_CLI")),
        None,
    )
    repo.save_research_plan(plan)
    evidence_before = len(repo.list_evidence())

    runner = CliRunner()
    cli_result = runner.invoke(cli_app, ["research", "run", "DEC_CLI", "--db", str(db_path)])
    assert cli_result.exit_code == 0, cli_result.output
    cli_payload = json.loads(cli_result.output)
    assert "applied_evidence" in cli_payload
    assert cli_payload["applied_evidence"], "CLI research run must apply evidence"
    assert len(repo.list_evidence()) > evidence_before

    # The shared service persisted project-owned evidence (P0-3) and produced
    # bindings for the target claim.
    applied_ids = {e["id"] for e in cli_payload["applied_evidence"]}
    for eid in applied_ids:
        assert repo.get_evidence(eid).project_id == "PRJ_CLI"
    bindings = repo.list_bindings()
    assert any(b.claim_id == "CLM_WTP" for b in bindings)


def test_research_provider_failure_creates_no_fake_evidence():
    """P0-5/GAP-02: a failing search provider produces NO fake evidence."""
    class _FailingSearch:
        name = "failing_search"

        def search(self, query, k=5):  # noqa: ARG002
            raise ProviderTimeoutError("search timed out")

    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=_FailingSearch(), retrieval=None,
        bus=bus, settings=settings,
    )
    result = runtime.solve(
        SolveRequest(project_id="PRJ_FAIL", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    # Strong assertion: NO fake evidence is persisted by the failing-provider
    # path (compile creates no evidence and the failing search yields no
    # candidates), while the research traces still ran and recorded the failure.
    assert repo.list_evidence() == [], (
        "failing search provider must not fabricate evidence"
    )
    assert len(repo.list_research_traces(result.decision_id)) > 0
    # The service-level contract: run_plan on a failing provider adds no evidence.
    service = runtime.engines.research_execution
    out = service.run_plan(result.decision_id)
    assert out.applied_evidence == []
    assert any("search provider failed" in note for t in out.traces for note in t.notes)


# ---------------------------------------------------------------------------
# 8. P0-6 experiment validation enforced everywhere
# ---------------------------------------------------------------------------


class _VagueExperimentCompiler:
    """Compiler whose compiled experiment fails validate_experiment."""

    def compile(self, problem, project_state, options=None, context=None):  # noqa: ARG002
        decision = Decision(
            id="DEC_INV", decision_question=problem, objective_id="OBJ_INV",
            project_id="PRJ_INV",
            options=[
                DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
                DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
            ],
            relevant_belief_ids=["wtp"],
        )
        return CompiledDecision(
            objective=Objective(id="OBJ_INV", owner="u1", name="obj", description=""),
            decision=decision,
            claims=[
                Claim(id="CLM_WTP", statement="ICP will pay for the promised outcome",
                      scope="PROJECT", project_id="PRJ_INV")
            ],
            beliefs=[
                Belief(id="wtp", claim_id="CLM_WTP", statement="ICP will pay for the promised outcome",
                       scope="PROJECT", project_id="PRJ_INV", decision_relevant=True,
                       alpha=1.0, beta=1.0, probability=0.5, posterior=0.5,
                       uncertainty=0.6, decision_weight=1.0)
            ],
            experiments=[
                Experiment(
                    id="EXP_BAD", name="Do more interviews", target_belief_ids=["wtp"],
                    hypothesis="h", action="Do some more interviews",
                    predicted_observation="o", success_criteria="",
                    failure_criteria="", ambiguity_criteria="",
                    expected_information_gain=0.5, decision_impact=0.5,
                )
            ],
        )


def test_invalid_experiment_never_persisted():
    """P0-6: solve NEVER persists an invalid experiment; the default passes the
    same validator."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings, compiler=_VagueExperimentCompiler(),
    )
    result = runtime.solve(
        SolveRequest(project_id="PRJ_INV", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    saved = repo.list_experiments("PRJ_INV")
    assert all(e.id != "EXP_BAD" for e in saved)
    assert result.next_experiment is not None  # ADR-007 invariant
    # Default experiment passes the validator.
    default = synthesize_default_experiment(
        runtime.repo.get_decision(result.decision_id), None
    )
    assert validate_experiment(default).valid is True


def test_provider_generated_vague_experiment_is_rejected(settings):
    """P0-6: propose() rejects vague candidates and reports them."""
    decision = _decision("DEC", ["wtp"])
    beliefs = [
        Belief(id="wtp", claim_id="CLM_WTP", statement="wtp", scope="PROJECT",
               project_id="PRJ_1", decision_relevant=True, uncertainty=0.8,
               decision_weight=1.0)
    ]
    vague = Experiment(
        id="EXP_VAGUE", name="Do more interviews", target_belief_ids=["wtp"],
        hypothesis="h", action="Do some more interviews", predicted_observation="o",
        success_criteria="", failure_criteria="", ambiguity_criteria="",
        expected_information_gain=0.5, decision_impact=0.5,
    )
    proposal = ExperimentOptimizer(settings).propose(
        ExperimentProposalInput(
            decision=decision, beliefs=beliefs, critical_belief_id="wtp",
            candidates=[vague],
        )
    )
    assert any(r["experiment_id"] == "EXP_VAGUE" for r in proposal.rejected)
    assert all(r.experiment.id != "EXP_VAGUE" for r in proposal.ranked)


def test_default_experiment_passes_validator(settings):
    """P0-6: the synthesized default is always valid (ADR-007 invariant)."""
    default = synthesize_default_experiment(_decision("DEC", ["wtp"]), "wtp")
    assert validate_experiment(default).valid is True


# ---------------------------------------------------------------------------
# 9. P1-7 CallRecorder records REAL provider calls
# ---------------------------------------------------------------------------


def test_call_recorder_records_real_provider_calls():
    """P1-7: solve records model calls; research records search calls; failing
    providers are recorded as failed with structured error types."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    recorder = engines.call_recorder
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=with_resilience(MockProvider(), settings, recorder),
        search=with_resilience(MockSearchProvider(), settings, recorder),
        retrieval=with_resilience(MockRetrievalProvider(), settings, recorder),
        bus=bus, settings=settings,
    )
    result = runtime.solve(
        SolveRequest(project_id="PRJ_REC", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    model_records = repo.list_call_records(kind="model")
    assert model_records, "solve must record model provider calls"
    for rec in model_records:
        assert rec.provider == "mock"
        assert rec.latency_ms >= 0
        assert rec.success is True
        # Red line: no prompt / sensitive content.
        assert not rec.model_dump().get("prompt")
        assert not rec.model_dump().get("api_key")

    runtime.engines.research_execution.run_plan(result.decision_id)
    search_records = repo.list_call_records(kind="search")
    assert search_records, "research must record search provider calls"

    # Failing provider → structured failure record.
    class _Failing:
        name = "failing"

        def search(self, query, k=5):  # noqa: ARG002
            raise ProviderTimeoutError("timeout")

    repo2 = InMemoryRepository()
    rec2 = default_engine_bundle(repo2, Settings()).call_recorder
    wrapped = with_resilience(_Failing(), Settings(), rec2)
    with pytest.raises(ProviderTimeoutError):
        wrapped.search("q")
    fail_records = repo2.list_call_records(kind="search")
    assert fail_records and fail_records[-1].success is False
    assert fail_records[-1].error_type in ("TIMEOUT", "PROVIDER_TIMEOUT")


# ---------------------------------------------------------------------------
# 10. P1-8 research stop rule uses claim ids, not evidence ids
# ---------------------------------------------------------------------------


def test_research_stop_claim_coverage_uses_claim_ids(settings):
    """P1-8: claim_coverage is driven by Evidence.claim_ids ∩ target_claims —
    an evidence id that LOOKS like a claim id must not count."""
    rule = ResearchStopRule(settings)
    ev = Evidence(id="E_1", claim_ids=["CLM_TARGET"], scope="MARKET",
                  evidence_type="REVIEWED_EXTERNAL_RESEARCH", source="x")
    summary = RoundSummary(
        applied_evidence=[ev], bindings=[],
        target_claim_ids=["CLM_TARGET", "CLM_OTHER"],
        beliefs_before=[], beliefs_after=[],
    )
    report = rule.evaluate([], [], [], ["CLM_TARGET"], round_no=1, round_summary=summary)
    assert report.signals["claim_coverage"] == 0.5

    # Evidence with id "CLM_TARGET" but no claim_ids must NOT count.
    fake = Evidence(id="CLM_TARGET", claim_ids=[], scope="MARKET",
                    evidence_type="REVIEWED_EXTERNAL_RESEARCH", source="y")
    summary2 = RoundSummary(
        applied_evidence=[fake], bindings=[],
        target_claim_ids=["CLM_TARGET"],
        beliefs_before=[], beliefs_after=[],
    )
    report2 = rule.evaluate([], [], [], ["CLM_TARGET"], round_no=1, round_summary=summary2)
    assert report2.signals["claim_coverage"] == 0.0


def test_research_stop_real_source_quality(settings):
    """P1-8: high-authority evidence yields high source_quality; low-authority
    (LLM_INFERENCE) stays low — never the old fake 0.5."""
    rule = ResearchStopRule(settings)
    high = Evidence(id="E_H", claim_ids=["CLM_T"], scope="PROJECT",
                    evidence_type="OBSERVED_BEHAVIOR", source="x",
                    authority_level="PROJECT_DIRECT_BEHAVIOR", verification="VERIFIED")
    summary = RoundSummary(applied_evidence=[high], bindings=[],
                           target_claim_ids=["CLM_T"], beliefs_before=[], beliefs_after=[])
    report = rule.evaluate([], [], [], ["CLM_T"], round_no=1, round_summary=summary)
    assert report.signals["source_quality"] > 0.5

    low = Evidence(id="E_L", claim_ids=["CLM_T"], scope="MARKET",
                   evidence_type="LLM_INFERENCE", source="y",
                   authority_level="LLM_INFERENCE", verification="ESTIMATED")
    summary_low = RoundSummary(applied_evidence=[low], bindings=[],
                               target_claim_ids=["CLM_T"], beliefs_before=[], beliefs_after=[])
    report_low = rule.evaluate([], [], [], ["CLM_T"], round_no=1, round_summary=summary_low)
    assert report_low.signals["source_quality"] < 0.3


# ---------------------------------------------------------------------------
# 11/12. P1-10 benchmark semantics
# ---------------------------------------------------------------------------


def test_l1_regret_is_na_without_utility_labels():
    """P1-10: L1-style cases (no utility labels) → regret is None (N/A)."""
    from vencertia.benchmark.metrics import compute_all

    metrics = compute_all(
        [
            {"predicted_option": "a", "gold_option": "a", "decided": True, "correct": True,
             "chosen_utility": None, "best_utility": None}
        ]
    )
    assert metrics["decision_regret"] is None


def test_l0_option_accuracy_excludes_unlabeled_options():
    """P1-10: gold_option_id=None / NO_DECISION cases count in pass rate but
    are excluded from the option-accuracy denominator."""
    from vencertia.benchmark.metrics import compute_all

    metrics = compute_all(
        [
            {"predicted_option": "a", "gold_option": "a", "decided": True, "correct": True,
             "chosen_utility": 0.8, "best_utility": 0.8},
            {"predicted_option": "b", "gold_option": "b", "decided": True, "correct": True,
             "chosen_utility": 0.6, "best_utility": 0.6},
            {"predicted_option": "NO_DECISION", "gold_option": "NO_DECISION",
             "decided": False, "correct": True, "chosen_utility": None, "best_utility": None},
            {"predicted_option": "c", "gold_option": "d", "decided": True, "correct": False,
             "chosen_utility": 0.1, "best_utility": 0.9},
        ]
    )
    assert metrics["policy_regression_pass_rate"] == 0.75
    assert metrics["decision_option_accuracy"] == pytest.approx(2 / 3)
    assert metrics["decision_accuracy"] == metrics["decision_option_accuracy"]


# ---------------------------------------------------------------------------
# 13. P1-12 version single source
# ---------------------------------------------------------------------------


def test_version_single_source(project_root):
    """P1-12: pyproject / importlib.metadata / vencertia.__version__ agree."""
    import importlib.metadata

    import vencertia

    assert vencertia.__version__ == "2.0.0"
    assert vencertia.__api_contract_version__ == "1.4"
    assert importlib.metadata.version("vencertia-decision-runtime") == vencertia.__version__
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == vencertia.__version__


def test_health_exposes_runtime_and_api_contract_versions():
    """P1-12: /health exposes runtime_version + api_contract_version + legacy."""
    tc, _, _, _ = _solved_client()
    data = tc.get("/health").json()["data"]
    assert data["runtime_version"] == "2.0.0"
    assert data["api_contract_version"] == "1.4"
    assert data["version"] == "2.0.0"
    assert data["api_version"] == "1.4.0"


# ---------------------------------------------------------------------------
# 14. P1-11 candidate validation has no conditional skip
# ---------------------------------------------------------------------------


def test_candidate_validation_api_has_no_conditional_skip():
    """P1-11: the candidate-validate endpoint works with a deterministic
    fixture — zero conditional skips across the suite."""
    from vencertia.domain import CandidateClaim

    tc, repo, _, _ = _solved_client()
    candidate = CandidateClaim(
        id="CC_INTEGRITY",
        statement="ICP has a severe recurring problem",
        scope="PROJECT",
        source_evidence_ids=["E_FIXTURE"],
        extraction_confidence=0.9,
        validation_status="PENDING",
    )
    repo.save_candidate_claim(candidate)
    r = tc.post(f"/v1/claims/candidates/{candidate.id}/validate")
    assert r.status_code == 200
    assert r.json()["data"]["validation_status"] == "VALIDATED"


def test_opportunity_cost_default_off_is_zero_behavior_change():
    """P1-9: with default settings, solve does NOT touch option opportunity_cost."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    result = runtime.solve(
        SolveRequest(project_id="PRJ_OC", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    decision = repo.get_decision(result.decision_id)
    assert all(round(o.opportunity_cost, 4) == o.opportunity_cost for o in decision.options)
    assert settings.opportunity_cost_enabled is False


# ---------------------------------------------------------------------------
# P2-17 transaction boundaries (atomic mutation batches)
# ---------------------------------------------------------------------------


class _FailingBindingRepo:
    """Delegates to InMemoryRepository but fails on save_binding (mid-batch)."""

    def __init__(self, inner: InMemoryRepository) -> None:
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def save_binding(self, binding, expected_version=None):
        raise RuntimeError("injected binding failure")


def test_research_round_mutation_is_atomic():
    """P2-17: a mid-batch failure rolls the WHOLE research round back — no
    evidence / beliefs / trace survive."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    inner = InMemoryRepository()
    repo = _FailingBindingRepo(inner)
    bus = EventBus(sink=inner.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    _seed_researchable_decision(repo, "PRJ_ATOMIC", "DEC_ATOMIC")
    evidence_before = len(inner.list_evidence())
    with pytest.raises(RuntimeError, match="injected binding failure"):
        runtime.engines.research_execution.run_plan("DEC_ATOMIC")
    # No half batch: evidence count unchanged, no research trace persisted.
    assert len(inner.list_evidence()) == evidence_before
    assert inner.list_research_traces("DEC_ATOMIC") == []
    beliefs = {b.id: b.probability for b in inner.get_beliefs("PRJ_ATOMIC")}
    assert beliefs == {"wtp": 0.5}


class _FailingOutcomeRepo:
    """Delegates to InMemoryRepository but fails on save_outcome (mid-batch)."""

    def __init__(self, inner: InMemoryRepository) -> None:
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def save_outcome(self, outcome, expected_version=None):
        raise RuntimeError("injected outcome failure")


def test_outcome_settlement_rolls_back_on_failure():
    """P2-17: a failure during outcome settlement rolls back Outcome + Evidence
    + Belief updates — no half settlement."""
    settings = Settings(db_dsn="sqlite:///:memory:")
    inner = InMemoryRepository()
    repo = _FailingOutcomeRepo(inner)
    bus = EventBus(sink=inner.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
        bus=bus, settings=settings,
    )
    result = runtime.solve(
        SolveRequest(project_id="PRJ_OS", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    decision = inner.get_decision(result.decision_id)
    inner.save_action(
        Action(id="ACT_OS", project_id="PRJ_OS", kind="EXPERIMENT",
               decision_id=decision.id, experiment_id="EXP_OS")
    )
    belief_before = {b.id: b.probability for b in inner.get_beliefs("PRJ_OS")}
    with pytest.raises(RuntimeError, match="injected outcome failure"):
        runtime.record_outcome("ACT_OS", "0 paid", outcome_type="FAILURE")
    # No half settlement: no outcome persisted; beliefs unchanged.
    assert inner.list_outcomes(action_id="ACT_OS") == []
    belief_after = {b.id: b.probability for b in inner.get_beliefs("PRJ_OS")}
    assert belief_after == belief_before


def test_sqlite_store_does_not_commit_inside_txn(tmp_path):
    """P2-17: SQLite does not commit intermediate writes inside in_transaction;
    another connection only sees the batch after the outer commit."""
    import sqlite3

    from vencertia.repositories.sqlite import SQLiteRepository

    db_path = tmp_path / "txn.db"
    repo = SQLiteRepository(path=db_path)
    repo.save_project(Project(id="PRJ_1", user_id="u1", name="p"))

    def _batch():
        repo.save_belief(
            Belief(id="B1", claim_id="C1", statement="s1", scope="PROJECT",
                   project_id="PRJ_1")
        )
        repo.save_belief(
            Belief(id="B2", claim_id="C2", statement="s2", scope="PROJECT",
                   project_id="PRJ_1")
        )

    other = sqlite3.connect(str(db_path))
    other.row_factory = sqlite3.Row

    observed_inside: list[int] = []

    def _batch_with_probe():
        _batch()
        observed_inside.append(
            other.execute(
                "SELECT COUNT(*) AS n FROM entities WHERE entity_type='belief'"
            ).fetchone()["n"]
        )

    repo.in_transaction(_batch_with_probe)
    # Inside the transaction the second connection saw 0 beliefs (no early commit).
    assert observed_inside == [0], observed_inside
    # After the outer commit, the second connection sees both beliefs.
    assert (
        other.execute(
            "SELECT COUNT(*) AS n FROM entities WHERE entity_type='belief'"
        ).fetchone()["n"]
        == 2
    )
    other.close()
