"""ContextBuilder tests: read-only projection."""

from __future__ import annotations

from vencertia.domain import Belief, Evidence, Project, Scope
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime.context import ContextBuilder


def test_context_bundle_projection(repo):
    repo.save_project(Project(id="PRJ_1", user_id="u1", name="Proj"))
    repo.save_belief(
        Belief(id="BLF_1", claim_id="CLM_1", statement="x", scope="PROJECT",
               project_id="PRJ_1", decision_relevant=True)
    )
    repo.add_evidence(
        Evidence(id="E_1", claim_ids=["CLM_1"], scope=Scope.PROJECT,
                 evidence_type="REAL_PAYMENT", source="paid", authority_level="PROJECT_REALITY")
    )
    bundle = ContextBuilder(repo).build("PRJ_1")
    assert bundle.project is not None
    assert bundle.project.id == "PRJ_1"
    assert bundle.project_snapshot["project_id"] == "PRJ_1"
    assert len(bundle.critical_assumptions) == 1
    assert len(bundle.top_evidence) == 1
    assert bundle.as_of is not None


def test_context_builder_missing_project(repo):
    bundle = ContextBuilder(repo).build("PRJ_NONE")
    assert bundle.project is None
    assert bundle.critical_assumptions == []
