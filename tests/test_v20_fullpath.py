"""v2.0 — full-path tests: idea intake → decision → business plan + skill layer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
from vencertia.config import Settings
from vencertia.events.bus import EventBus
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.runtime import SolveOrchestrator, default_engine_bundle
from vencertia.skills import (
    SkillCandidate,
    SkillRouter,
    SkillValidationError,
    build_biz_skill_registry,
)


@pytest.fixture
def client_and_repo():
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    runtime = SolveOrchestrator(
        repo=repo,
        policy=engines.evidence_policy,
        engines=engines,
        model=MockProvider(),
        search=MockSearchProvider(),
        retrieval=MockRetrievalProvider(),
        bus=bus,
        settings=settings,
    )
    return TestClient(create_app(settings, repo, runtime)), repo


# -- idea intake -----------------------------------------------------------------


def test_idea_assess_returns_structure(client_and_repo):
    client, _ = client_and_repo
    r = client.post(
        "/v1/ideas/assess",
        json={"idea_text": "做一个帮小店主自动对账的工具"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["decision_question"]
    assert data["recommended_mode_zh"]
    assert data["assumptions"], "assumption register must be non-empty"
    assert "solve_request" in data
    assert data["solve_request"]["mode"] == "EXPLORE"
    assert data["disclaimer"]


def test_idea_then_solve_full_path(client_and_repo):
    client, repo = client_and_repo
    idea = client.post(
        "/v1/ideas/assess",
        json={"idea_text": "做一个帮小店主自动对账的工具"},
    ).json()["data"]
    r = client.post(
        "/v1/solve?view=summary",
        json=idea["solve_request"],
    )
    assert r.status_code == 200, r.text
    summary = r.json()["data"]
    assert summary["current_judgment_zh"]
    # the review ledger now carries the decision
    review = client.get("/v1/review").json()["data"]
    assert any(row["decision_id"] for row in review["ledger"])


# -- business plan ---------------------------------------------------------------


def _solved_decision_id(client, pid: str) -> str:
    client.post("/v1/solve?view=summary", json={"project_id": pid, "problem_text": "是否投入 6 周做 MVP？"})
    review = client.get("/v1/review").json()["data"]
    return [r for r in review["ledger"] if r.get("decision_id")][0]["decision_id"]


def test_bp_generates_sections_and_narratives(client_and_repo):
    client, _ = client_and_repo
    decision_id = _solved_decision_id(client, "PRJ_BP20")
    r = client.post(
        "/v1/bp",
        json={"decision_id": decision_id, "company_name": "小店对账科技"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    view = data["view"]
    assert view["company_name"] == "小店对账科技"
    titles = [s["title_zh"] for s in view["sections"]]
    for expected in ("执行摘要", "市场机会", "为什么是我们", "关键假设与风险", "计划与里程碑", "什么会推翻这个计划", "复盘与校准"):
        assert expected in titles
    # honesty: market section is N/A when there is no market evidence
    market = next(s for s in view["sections"] if s["key"] == "market_opportunity")
    assert market["na"] is True
    assert data["markdown"].startswith("# ")
    # v2.0.1: with an explicitly-mock provider there is NO template narrative —
    # every narrative skill is honestly REJECTED (never fabricates AI output).
    assert data["narratives"] == []
    rejected = {t["skill"] for t in data["skill_traces"] if t["status"] == "REJECTED"}
    assert rejected == {"market_opportunity", "financial_model", "plan_narrative"}


def test_skill_router_ok_with_stub_model():
    """The OK path: skills pass contract+reference gates with a working model."""
    from vencertia.skills import SkillMetadata
    from vencertia.skills.base import SkillRegistry
    from vencertia.skills.biz import (
        FinancialModelSkill,
        MarketOpportunitySkill,
        PlanNarrativeSkill,
    )

    class _StubModel:
        name = "stub"

        def generate_structured(self, task, schema, context):
            kind = schema["kind"]
            if kind == "MarketOpportunityContract":
                return {"thesis": "t", "items": []}
            if kind == "FinancialModelContract":
                return {"unit_economics": "u", "assumptions": [], "milestones": []}
            if kind == "PlanNarrativeContract":
                return {"sections": []}
            raise ValueError(f"unexpected kind {kind}")

    stub = _StubModel()
    registry = SkillRegistry()
    for skill_cls, name, source in (
        (MarketOpportunitySkill, "market_opportunity", "Vencertia_Market_Opportunity_V11_v0.1.docx"),
        (FinancialModelSkill, "financial_model", "Vencertia_Financial_and_Business_Model_V11_v0.1.docx"),
        (PlanNarrativeSkill, "plan_narrative", "Vencertia_Business_Plan_Architect_V11_v0.1.docx"),
    ):
        registry.register(
            skill_cls(model=stub),
            SkillMetadata(
                name=name, version="v11.0", v11_source=source, description="d",
                contract=skill_cls.contract, stage="bp",
            ),
        )
    candidates, traces = SkillRouter(registry).run_stage("bp", {"claim_ids": ["CLM_A"]})
    assert len(candidates) == 3
    assert all(not c.deterministic for c in candidates)
    assert all(t.status == "OK" for t in traces)


def test_bp_unknown_decision_404(client_and_repo):
    client, _ = client_and_repo
    r = client.post("/v1/bp", json={"decision_id": "DEC_MISSING"})
    assert r.status_code == 404


def test_bp_market_section_has_data_after_market_evidence(client_and_repo):
    client, repo = client_and_repo
    decision_id = _solved_decision_id(client, "PRJ_BP20B")
    from vencertia.domain import Evidence

    decision = repo.get_decision(decision_id)
    market_beliefs = [b for b in repo.get_beliefs(decision.project_id) if str(b.scope) == "MARKET"]
    repo.add_evidence(
        Evidence(
            id="E_MKT_20",
            claim_ids=[b.claim_id for b in market_beliefs] or ["CLM_NONE"],
            scope="MARKET",
            evidence_type="REVIEWED_EXTERNAL_RESEARCH",
            source="行业报告",
            strength=0.8,
            directness=0.7,
            reliability=0.7,
            relevance=0.7,
        )
    )
    r = client.post("/v1/bp", json={"decision_id": decision_id})
    market = next(
        s for s in r.json()["data"]["view"]["sections"] if s["key"] == "market_opportunity"
    )
    assert market["na"] is False or market["bullets"] or market["lines"]


# -- skill layer -----------------------------------------------------------------


def test_skills_catalog_endpoint(client_and_repo):
    client, _ = client_and_repo
    r = client.get("/v1/skills")
    assert r.status_code == 200
    skills = r.json()["data"]
    names = {s["name"] for s in skills}
    assert names == {
        "market_opportunity",
        "financial_model",
        "plan_narrative",
        "founder_diagnosis",
        "execution_strategy",
    }
    assert all(s["version"] == "v11.0" for s in skills)
    assert all(s["v11_source"].startswith("Vencertia_") for s in skills)


def test_skill_router_rejects_unreferenced_claim():
    registry = build_biz_skill_registry()
    router = SkillRouter(registry)

    class _BadSkill:
        contract = "MarketOpportunityContract"

        def run(self, context):
            return SkillCandidate(
                skill="bad_market",
                version="v11.0",
                contract=self.contract,
                payload={
                    "thesis": "x",
                    "items": [
                        {
                            "claim_id": "CLM_NOT_IN_CONTEXT",
                            "statement": "s",
                            "evidence_summary": "",
                            "numbers": [],
                        }
                    ],
                },
                deterministic=False,
            )

    from vencertia.skills.base import SkillMetadata

    registry.register(
        _BadSkill(),
        SkillMetadata(
            name="bad_market", version="v11.0", v11_source="x",
            description="bad", contract="MarketOpportunityContract", stage="bp",
        ),
    )
    candidates, traces = router.run_stage("bp", {"claim_ids": ["CLM_OK"]})
    assert all(c.skill != "bad_market" for c in candidates)
    bad_trace = next(t for t in traces if t.skill == "bad_market")
    assert bad_trace.status == "REJECTED"
    assert "不存在的 claim" in bad_trace.note


def test_skill_router_contract_validation():
    registry = build_biz_skill_registry()
    router = SkillRouter(registry)

    class _BadContract:
        contract = "FinancialModelContract"

        def run(self, context):
            return SkillCandidate(
                skill="bad_fin", version="v11.0", contract=self.contract,
                payload={"assumptions": [{"label": "x", "value": "1", "note": ""}]},  # missing source_claim_id
                deterministic=False,
            )

    from vencertia.skills.base import SkillMetadata

    registry.register(
        _BadContract(),
        SkillMetadata(
            name="bad_fin", version="v11.0", v11_source="x", description="bad",
            contract="FinancialModelContract", stage="bp",
        ),
    )
    _, traces = router.run_stage("bp", {"claim_ids": ["CLM_OK"]})
    bad = next(t for t in traces if t.skill == "bad_fin")
    assert bad.status == "REJECTED"


def test_validate_references_raises_for_fake_id():
    from vencertia.skills import validate_references

    candidate = SkillCandidate(
        skill="x", version="v11.0", contract="ExecutionStrategyContract",
        payload={"steps": [{"step": "s", "rationale": "r", "source_claim_id": "CLM_FAKE"}]},
        deterministic=False,
    )
    with pytest.raises(SkillValidationError):
        validate_references(candidate, {"claim_ids": ["CLM_REAL"]})


# -- UI wiring -------------------------------------------------------------------


def test_ui_wires_idea_and_bp(api_client):
    js = api_client.get("/static/app.js")
    assert js.status_code == 200
    for marker in ("评估想法", "生成 BP", "复制全文", "/v1/ideas/assess", "/v1/bp"):
        assert marker in js.text
    html = api_client.get("/")
    assert "idea-text" in html.text
    assert "bp-panel" in html.text
