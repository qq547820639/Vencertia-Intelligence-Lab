"""v1.3 T3 — model transparency (belief edge relation_zh + parameter provenance)."""

from __future__ import annotations

from vencertia.capabilities import CompiledDecision
from vencertia.domain import (
    ApprovalStatus,
    Belief,
    BeliefEdge,
    BeliefRelationType,
    Claim,
    Decision,
    DecisionOption,
    ModelParameter,
    Objective,
    Project,
    ProvenanceType,
)
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest
from vencertia.runtime.presentation import solve_summary


class _ProvenanceCompiler:
    """Compiler returning options with provenance-annotated belief parameters."""

    def compile(self, problem, project_state, options=None, context=None):  # noqa: ARG002
        decision = Decision(
            id="DEC_PROV",
            decision_question=problem,
            objective_id="OBJ_PROV",
            project_id="PRJ_PROV",
            options=[
                DecisionOption(
                    id="go",
                    label="Go",
                    belief_parameters={
                        "b1": ModelParameter(
                            value=0.8,
                            provenance=ProvenanceType.USER_DEFINED,
                            status=ApprovalStatus.APPROVED,
                        ),
                        "b2": ModelParameter(
                            value=0.3,
                            provenance=ProvenanceType.LLM_PROPOSED,
                            status=ApprovalStatus.PROPOSED,
                        ),
                        "b3": ModelParameter(
                            value=0.5,
                            provenance=ProvenanceType.UNKNOWN,
                            status=ApprovalStatus.APPROVED,
                        ),
                    },
                ),
                DecisionOption(id="hold", label="Hold", belief_coefficients={"b1": 0.1}),
            ],
            relevant_belief_ids=["b1", "b2", "b3"],
        )
        return CompiledDecision(
            objective=Objective(id="OBJ_PROV", owner="u1", name="obj", description=""),
            decision=decision,
            claims=[
                Claim(id="CLM_1", statement="s1", scope="PROJECT", project_id="PRJ_PROV"),
                Claim(id="CLM_2", statement="s2", scope="PROJECT", project_id="PRJ_PROV"),
                Claim(id="CLM_3", statement="s3", scope="PROJECT", project_id="PRJ_PROV"),
            ],
            beliefs=[
                Belief(
                    id="b1", claim_id="CLM_1", statement="s1", scope="PROJECT",
                    project_id="PRJ_PROV", decision_relevant=True, alpha=1.0, beta=1.0,
                    probability=0.5, posterior=0.5, uncertainty=0.5, decision_weight=1.0,
                ),
                Belief(
                    id="b2", claim_id="CLM_2", statement="s2", scope="PROJECT",
                    project_id="PRJ_PROV", decision_relevant=True, alpha=1.0, beta=1.0,
                    probability=0.5, posterior=0.5, uncertainty=0.5, decision_weight=1.0,
                ),
                Belief(
                    id="b3", claim_id="CLM_3", statement="s3", scope="PROJECT",
                    project_id="PRJ_PROV", decision_relevant=True, alpha=1.0, beta=1.0,
                    probability=0.5, posterior=0.5, uncertainty=0.5, decision_weight=1.0,
                ),
            ],
            experiments=[],
        )


def _orchestrator_with_provenance() -> tuple[SolveOrchestrator, InMemoryRepository]:
    repo = InMemoryRepository()
    repo.save_project(Project(id="PRJ_PROV", user_id="u1", name="p"))
    repo.save_belief_edge(
        BeliefEdge(
            id="BE_1", project_id="PRJ_PROV", source_belief_id="b1",
            target_belief_id="b2", relation=BeliefRelationType.UNKNOWN_RELATIONSHIP,
        )
    )
    repo.save_belief_edge(
        BeliefEdge(
            id="BE_2", project_id="PRJ_PROV", source_belief_id="b2",
            target_belief_id="b3", relation=BeliefRelationType.CAUSES,
        )
    )
    bus = EventBus(sink=repo.append_event)
    orchestrator = SolveOrchestrator(
        repo=repo, bus=bus, compiler=_ProvenanceCompiler(),
        model=MockProvider(), search=MockSearchProvider(), retrieval=MockRetrievalProvider(),
    )
    return orchestrator, repo


def test_belief_graph_edge_relation_zh():
    orchestrator, _ = _orchestrator_with_provenance()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_PROV", problem_text="Should we commit?", user_id="u1")
    )
    edges = result.advanced_view.belief_graph
    assert len(edges) == 2
    by_id = {e["id"]: e for e in edges}
    assert by_id["BE_1"]["relation"] == "UNKNOWN_RELATIONSHIP"
    assert by_id["BE_1"]["relation_zh"] == "关系未知"
    assert by_id["BE_2"]["relation"] == "CAUSES"
    assert by_id["BE_2"]["relation_zh"] == "因果关系"


def test_parameter_provenance_chinese():
    orchestrator, _ = _orchestrator_with_provenance()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_PROV", problem_text="Should we commit?", user_id="u1")
    )
    prov = result.advanced_view.parameter_provenance
    by_belief = {p["belief_id"]: p for p in prov}
    assert by_belief["b1"]["provenance_zh"] == "由你设定"
    assert by_belief["b2"]["provenance_zh"] == "模型建议，未经你确认"
    assert by_belief["b3"]["provenance_zh"] == "来源未知"


def test_llm_proposed_needs_confirmation():
    orchestrator, _ = _orchestrator_with_provenance()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_PROV", problem_text="Should we commit?", user_id="u1")
    )
    prov = result.advanced_view.parameter_provenance
    llm = [p for p in prov if p["provenance"] == "LLM_PROPOSED"]
    assert llm and all(p["needs_confirmation"] is True for p in llm)
    user = [p for p in prov if p["provenance"] == "USER_DEFINED"]
    assert user and all(p["needs_confirmation"] is False for p in user)


def test_summary_transparency_section_linked():
    orchestrator, _ = _orchestrator_with_provenance()
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_PROV", problem_text="Should we commit?", user_id="u1")
    )
    s = solve_summary(result)
    assert s["belief_dependencies"], "summary must surface belief edges"
    assert all("relation_zh" in e for e in s["belief_dependencies"])
    assert s["provenance_summary"] == result.advanced_view.parameter_provenance
    assert any(p["provenance"] == "LLM_PROPOSED" for p in s["provenance_summary"])
