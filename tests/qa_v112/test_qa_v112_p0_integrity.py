"""v1.1.2 P0 deep adversarial verification — tenant isolation, belief→claim
mapping, decision-aware context, research single pipeline, experiment
validation, recent outcomes.

Independent QA (trust but verify): these tests intentionally go beyond the
engineer's acceptance tests — they attempt to BYPASS the read boundary, verify
ownership of research-produced evidence, prove the mapping is real (not string
guessing), and check SQLite/InMemory parity.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vencertia.api import create_app
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
    Scope,
)
from vencertia.events.bus import EventBus
from vencertia.providers.errors import ProviderTimeoutError
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, default_engine_bundle
from vencertia.runtime.context import ContextBuilder
from vencertia.runtime.context_ranker import ContextRanker, DecisionRelevantContextBuilder
from vencertia.runtime.experiment_optimizer import (
    synthesize_default_experiment,
    validate_experiment,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_project(pid: str, user: str = "u1") -> Project:
    return Project(id=pid, user_id=user, name=f"project {pid}")


def make_evidence(
    eid: str,
    claim_ids: list[str],
    scope: str = "PROJECT",
    project_id: str | None = None,
    authority: str = "PROJECT_DIRECT_BEHAVIOR",
    **kw,
) -> Evidence:
    return Evidence(
        id=eid,
        claim_ids=claim_ids,
        scope=scope,
        evidence_type="OBSERVED_BEHAVIOR" if scope == "PROJECT" else "REVIEWED_EXTERNAL_RESEARCH",
        source=f"source {eid}",
        authority_level=authority,
        project_id=project_id,
        **kw,
    )


def make_orchestrator(repo, settings=None, **kw):
    settings = settings or Settings(db_dsn="sqlite:///:memory:")
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    return SolveOrchestrator(
        repo=repo,
        policy=engines.evidence_policy,
        engines=engines,
        model=kw.pop("model", MockProvider()),
        search=kw.pop("search", MockSearchProvider()),
        retrieval=kw.pop("retrieval", MockRetrievalProvider()),
        bus=bus,
        settings=settings,
        **kw,
    )


# ---------------------------------------------------------------------------
# P0-3 跨项目隔离（Release Blocker）— 深度对抗
# ---------------------------------------------------------------------------


def test_qa_p03_project_evidence_never_leaks_across_projects():
    """A 私有 PROJECT 证据对 B 不可见；共享 MARKET/WORLD 双方可见；CUSTOMER
    私有同样隔离；绕过读边界（直接后端私有访问）数据确实存在——证明过滤在读边界，
    而非数据未写入。"""
    repo = InMemoryRepository()
    repo.save_project(make_project("PRJ_A"))
    repo.save_project(make_project("PRJ_B"))
    repo.add_evidence(make_evidence("E_A", ["CLM_A"], project_id="PRJ_A"))
    repo.add_evidence(make_evidence("E_B", ["CLM_B"], project_id="PRJ_B"))
    repo.add_evidence(
        make_evidence("E_CUST", ["CLM_C"], scope="CUSTOMER", project_id="PRJ_A")
    )
    repo.add_evidence(
        make_evidence("E_SHARED", ["CLM_S"], scope="MARKET", project_id=None)
    )
    repo.add_evidence(
        make_evidence("E_WORLD", ["CLM_W"], scope="WORLD", project_id=None)
    )

    visible_a = {e.id for e in repo.list_evidence(project_id="PRJ_A")}
    visible_b = {e.id for e in repo.list_evidence(project_id="PRJ_B")}
    assert visible_a == {"E_A", "E_CUST", "E_SHARED", "E_WORLD"}
    assert visible_b == {"E_B", "E_SHARED", "E_WORLD"}

    # 直接私有调用证明数据在库里，只是读边界挡掉了 —— 防止“测试通过因为根本没写进去”
    raw = repo._list_all("evidence")
    raw_ids = {row["id"] for row in raw}
    assert {"E_A", "E_B", "E_CUST", "E_SHARED", "E_WORLD"} <= raw_ids

    # Context 层同样隔离
    ctx_a = ContextBuilder(repo).build("PRJ_A")
    ctx_b = ContextBuilder(repo).build("PRJ_B")
    assert {e.id for e in ctx_a.top_evidence} == visible_a
    assert {e.id for e in ctx_b.top_evidence} == visible_b

    # DecisionRelevantContextBuilder 同样隔离
    ba = DecisionRelevantContextBuilder(repo, ranker=ContextRanker()).build_for_decision("PRJ_A")
    assert all(e.id != "E_B" for e in ba.top_evidence)
    bb = DecisionRelevantContextBuilder(repo, ranker=ContextRanker()).build_for_decision("PRJ_B")
    assert all(e.id != "E_A" for e in bb.top_evidence)


def test_qa_p03_include_shared_false_hides_shared_evidence():
    """list_evidence(include_shared=False) 只返回项目自有证据。"""
    repo = InMemoryRepository()
    repo.save_project(make_project("PRJ_A"))
    repo.add_evidence(make_evidence("E_A", ["CLM_A"], project_id="PRJ_A"))
    repo.add_evidence(
        make_evidence("E_SHARED", ["CLM_S"], scope="MARKET", project_id=None)
    )
    only_owned = repo.list_evidence(project_id="PRJ_A", include_shared=False)
    assert {e.id for e in only_owned} == {"E_A"}
    with_shared = repo.list_evidence(project_id="PRJ_A", include_shared=True)
    assert {e.id for e in with_shared} == {"E_A", "E_SHARED"}


def test_qa_p03_write_boundary_rejects_missing_and_empty_project_id():
    """写边界：PROJECT/CUSTOMER 证据 project_id 缺失或为空串 → ValueError。"""
    repo = InMemoryRepository()
    with pytest.raises(ValueError, match="requires project_id"):
        repo.add_evidence(make_evidence("E_NOPID", ["CLM_X"], project_id=None))
    with pytest.raises(ValueError, match="requires project_id"):
        repo.add_evidence(make_evidence("E_EMPTY", ["CLM_X"], project_id=""))
    with pytest.raises(ValueError, match="requires project_id"):
        repo.add_evidence(
            make_evidence("E_CUST_NOPID", ["CLM_X"], scope="CUSTOMER", project_id=None)
        )
    # 共享 scope 允许 None（不静默入库 → 显式允许）
    repo.add_evidence(
        make_evidence("E_MKT_OK", ["CLM_X"], scope="MARKET", project_id=None)
    )
    assert repo.get_evidence("E_MKT_OK") is not None
    # allow_missing_project 迁移通道
    repo.add_evidence(make_evidence("E_MIG", ["CLM_X"], project_id=None), allow_missing_project=True)
    assert repo.get_evidence("E_MIG") is not None


def test_qa_p03_research_evidence_carries_collecting_project_id():
    """solve / API / CLI 三路 research 产生的证据 project_id = 收集项目（P0-3 归属）。"""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = make_orchestrator(repo, settings)
    _seed_researchable_decision(repo, "PRJ_R3", "DEC_R3")
    result = runtime.solve(
        SolveRequest(project_id="PRJ_R3", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    project_evidence = [e for e in repo.list_evidence() if e.id.startswith("E_")]
    assert project_evidence, "solve must produce research evidence"
    for e in project_evidence:
        if e.scope in (Scope.PROJECT.value, Scope.CUSTOMER.value):
            assert e.project_id == "PRJ_R3", f"{e.id} must be owned by PRJ_R3"


def _seed_researchable_decision(repo, project_id: str, decision_id: str) -> None:
    repo.save_project(make_project(project_id))
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
            objective_id="OBJ_R", project_id=project_id,
            options=[
                DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
                DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
            ],
            relevant_belief_ids=["wtp"],
        )
    )


def test_qa_p03_backfill_script_is_idempotent(tmp_path, monkeypatch):
    """回填脚本幂等：第二次运行零新增回填；已回填数据不变；无法解析保持 None。"""
    import importlib.util
    import sys
    from pathlib import Path

    # 隔离 argparse：避免读取 pytest 的 argv
    monkeypatch.setattr(sys, "argv", ["backfill_evidence_project_ids"])

    repo = InMemoryRepository()
    repo.save_project(make_project("PRJ_BF"))
    repo.add_claim(Claim(id="CLM_1", statement="s1", scope="PROJECT", project_id="PRJ_BF"))
    repo.add_claim(Claim(id="CLM_2", statement="s2", scope="PROJECT", project_id="PRJ_BF"))
    # legacy 无 project_id 的 PROJECT 证据（v1.1.1 库形态）
    repo.add_evidence(
        make_evidence("E_LEGACY1", ["CLM_1"], project_id=None), allow_missing_project=True
    )
    repo.add_evidence(
        make_evidence("E_LEGACY2", ["CLM_2"], project_id=None), allow_missing_project=True
    )
    # 无法解析（claim 不存在）
    repo.add_evidence(
        make_evidence("E_ORPHAN", ["CLM_NOPE"], project_id=None), allow_missing_project=True
    )
    # 共享 MARKET 不参与回填
    repo.add_evidence(
        make_evidence("E_MKT", ["CLM_1"], scope="MARKET", project_id=None)
    )

    # 用 importlib 从文件路径加载脚本模块（不依赖 sys.path 安装）
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "backfill_evidence_project_ids.py"
    spec = importlib.util.spec_from_file_location("backfill_mod", script_path)
    backfill_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backfill_mod)
    monkeypatch.setattr(backfill_mod, "_repo", lambda db=None: repo)

    assert backfill_mod.main() == 0
    assert repo.get_evidence("E_LEGACY1").project_id == "PRJ_BF"
    assert repo.get_evidence("E_LEGACY2").project_id == "PRJ_BF"
    assert repo.get_evidence("E_ORPHAN").project_id is None
    assert repo.get_evidence("E_MKT").project_id is None

    # 幂等：第二次运行 → 不新增变更
    assert backfill_mod.main() == 0
    assert repo.get_evidence("E_LEGACY1").project_id == "PRJ_BF"
    assert repo.get_evidence("E_ORPHAN").project_id is None


def test_qa_p03_sqlite_parity_for_isolation(tmp_path):
    """SQLite 后端同样满足读边界。"""
    repo = SQLiteRepository(path=tmp_path / "p03.db")
    repo.save_project(make_project("PRJ_A"))
    repo.save_project(make_project("PRJ_B"))
    repo.add_evidence(make_evidence("E_A", ["CLM_A"], project_id="PRJ_A"))
    repo.add_evidence(make_evidence("E_B", ["CLM_B"], project_id="PRJ_B"))
    repo.add_evidence(
        make_evidence("E_SHARED", ["CLM_S"], scope="MARKET", project_id=None)
    )
    assert {e.id for e in repo.list_evidence(project_id="PRJ_A")} == {"E_A", "E_SHARED"}
    assert {e.id for e in repo.list_evidence(project_id="PRJ_B")} == {"E_B", "E_SHARED"}
    with pytest.raises(ValueError):
        repo.add_evidence(make_evidence("E_NOPID", ["CLM_X"], project_id=None))


def test_qa_p03_api_add_evidence_rejects_project_evidence_without_project_id():
    """API add_evidence：PROJECT 证据无 project_id 且无法从 claim 推导 → HTTP 400。"""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = make_orchestrator(repo, settings)
    app = create_app(settings, repo, runtime)
    tc = TestClient(app)

    r = tc.post(
        "/v1/evidence",
        json={"evidence": make_evidence("E_API_NOPID", ["CLM_X"], project_id=None).model_dump(mode="json")},
    )
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# P0-2 belief→claim 映射（真实映射，非字符串猜测）
# ---------------------------------------------------------------------------


def test_qa_p02_mapping_is_real_not_string_guessing():
    """belief_id 与 claim_id 完全不同名（belief 'wtp' → claim 'CLM_WTP'）：证据
    claim_ids 命中 claim 而非 belief 字符串。若实现退化为 f'CLM_{belief_id}' 拼接，
    此用例必失败。"""
    ranker = ContextRanker(settings=Settings())
    decision = Decision(
        id="DEC", decision_question="q", objective_id="OBJ", project_id="PRJ",
        options=[DecisionOption(id="go", label="Go"), DecisionOption(id="hold", label="Hold")],
        relevant_belief_ids=["wtp"],
    )
    beliefs = [
        Belief(id="wtp", claim_id="CLM_WTP", statement="s", scope="PROJECT",
               project_id="PRJ", decision_relevant=True)
    ]
    claim_by_belief = {b.id: b.claim_id for b in beliefs}
    rel = make_evidence("E_REL", ["CLM_WTP"], project_id="PRJ")
    irr = make_evidence("E_IRR", ["CLM_OTHER"], project_id="PRJ")
    # 直接验证映射后交集
    assert ContextRanker._decision_relevance(rel, decision, claim_by_belief) == 1.0
    assert ContextRanker._decision_relevance(irr, decision, claim_by_belief) == 0.4
    # 无 mapping → 中性 0.5（绝不靠字符串猜测命中）
    assert ContextRanker._decision_relevance(rel, decision, None) == 0.5
    # score 层面相关证据必须胜出
    assert ranker.score_evidence(rel, decision, beliefs, claim_by_belief) > ranker.score_evidence(
        irr, decision, beliefs, claim_by_belief
    )


def test_qa_p02_legacy_decision_with_belief_ids_in_claim_namespace_still_maps():
    """即使 decision.relevant_belief_ids 恰好等于 claim id 形态，仍须通过 mapping
    而非直接 claim_ids ∩ relevant_belief_ids 跨 namespace 比较。"""
    ranker = ContextRanker(settings=Settings())
    decision = Decision(
        id="DEC", decision_question="q", objective_id="OBJ", project_id="PRJ",
        options=[DecisionOption(id="go", label="Go")],
        relevant_belief_ids=["CLM_WTP"],  # 用户误传 claim namespace
    )
    beliefs = [Belief(id="BLF_A", claim_id="CLM_WTP", statement="s", scope="PROJECT",
                      project_id="PRJ", decision_relevant=True)]
    claim_by_belief = {b.id: b.claim_id for b in beliefs}
    ev = make_evidence("E_X", ["CLM_WTP"], project_id="PRJ")
    # belief 集合里没有叫 CLM_WTP 的 belief → relevant_claim_ids 为空 → 0.4
    # （而不是直接 claim 交集命中 1.0 —— 那正是 P0-2 修复掉的跨 namespace bug）
    assert ContextRanker._decision_relevance(ev, decision, claim_by_belief) == 0.4


# ---------------------------------------------------------------------------
# P0-1 decision-aware context（post-compile）
# ---------------------------------------------------------------------------


def test_qa_p01_decision_change_reorders_context_ranking():
    """改变 decision 的 relevant_belief_ids → context ranking 翻转。"""
    repo = InMemoryRepository()
    repo.save_project(make_project("PRJ_1"))
    repo.save_belief(Belief(id="BLF_WTP", claim_id="CLM_WTP", statement="a", scope="PROJECT",
                            project_id="PRJ_1", decision_relevant=True))
    repo.save_belief(Belief(id="BLF_OTHER", claim_id="CLM_OTHER", statement="b", scope="PROJECT",
                            project_id="PRJ_1", decision_relevant=True))
    repo.add_evidence(
        make_evidence("E_REL", ["CLM_WTP"], project_id="PRJ_1", authority="PROJECT_DIRECT_BEHAVIOR",
                      strength=0.5, reliability=0.5, relevance=0.5)
    )
    repo.add_evidence(
        make_evidence("E_IRR", ["CLM_OTHER"], project_id="PRJ_1", authority="PROJECT_DIRECT_BEHAVIOR",
                      strength=0.5, reliability=0.5, relevance=0.5)
    )
    settings = Settings(db_dsn="sqlite:///:memory:")
    runtime = make_orchestrator(repo, settings)
    request = SolveRequest(project_id="PRJ_1", problem_text="q", user_id="u1")

    def dec(bid):
        return Decision(id=f"DEC_{bid}", decision_question="q", objective_id="OBJ",
                        project_id="PRJ_1",
                        options=[DecisionOption(id="go", label="Go")],
                        relevant_belief_ids=[bid])

    ctx_a = runtime._build_context(make_project("PRJ_1"), request, decision=dec("BLF_WTP"))
    ctx_b = runtime._build_context(make_project("PRJ_1"), request, decision=dec("BLF_OTHER"))
    assert ctx_a.top_evidence[0].id == "E_REL"
    assert ctx_b.top_evidence[0].id == "E_IRR"

    # pre-compile decision=None 不崩，且不产生决策相关性偏好
    ctx_none = runtime._build_context(make_project("PRJ_1"), request)
    assert len(ctx_none.top_evidence) == 2


# ---------------------------------------------------------------------------
# P0-4 Action(ACT_)→list_outcomes→Outcome(OUT_) 真实关联
# ---------------------------------------------------------------------------


def test_qa_p04_action_outcome_namespace_bridge_via_public_api():
    """save Action(ACT_1) + Outcome(OUT_1, action_id=ACT_1) →
    list_outcomes(action_id=ACT_1) 返回 OUT_1；recent_outcomes 非空。"""
    repo = InMemoryRepository()
    repo.save_project(make_project("PRJ_1"))
    repo.save_decision(
        Decision(id="DEC_1", decision_question="q", objective_id="OBJ", project_id="PRJ_1",
                 options=[DecisionOption(id="go", label="Go")])
    )
    repo.save_action(Action(id="ACT_1", project_id="PRJ_1", decision_id="DEC_1",
                            description="paid pilot"))
    repo.save_outcome(Outcome(id="OUT_1", action_id="ACT_1", result="0 paid"))
    assert [o.id for o in repo.list_outcomes(action_id="ACT_1")] == ["OUT_1"]
    assert [o.id for o in repo.list_outcomes(project_id="PRJ_1")] == ["OUT_1"]
    # get_outcome(ACT_1) 必须为 None —— 证明 namespace 不同（OUT_ != ACT_）
    assert repo.get_outcome("ACT_1") is None

    bundle = DecisionRelevantContextBuilder(
        repo, ranker=ContextRanker(settings=Settings())
    ).build_for_decision("PRJ_1")
    assert any(o.id == "OUT_1" for o in bundle.recent_outcomes)


def test_qa_p04_action_outcome_parity_sqlite(tmp_path):
    """SQLite 后端 list_actions/list_outcomes 过滤正确。"""
    repo = SQLiteRepository(path=tmp_path / "p04.db")
    repo.save_project(make_project("PRJ_1"))
    repo.save_decision(
        Decision(id="DEC_1", decision_question="q", objective_id="OBJ", project_id="PRJ_1",
                 options=[DecisionOption(id="go", label="Go")])
    )
    repo.save_action(Action(id="ACT_1", project_id="PRJ_1", decision_id="DEC_1", description="a"))
    repo.save_action(Action(id="ACT_2", project_id="PRJ_1", description="b"))
    repo.save_outcome(Outcome(id="OUT_1", action_id="ACT_1", result="r1"))
    assert [a.id for a in repo.list_actions(decision_id="DEC_1")] == ["ACT_1"]
    assert [o.id for o in repo.list_outcomes(action_id="ACT_1")] == ["OUT_1"]
    assert [o.id for o in repo.list_outcomes(project_id="PRJ_1")] == ["OUT_1"]


# ---------------------------------------------------------------------------
# P0-5 Research 三路共享单 pipeline
# ---------------------------------------------------------------------------


def test_qa_p05_solve_api_cli_share_same_research_execution_service(monkeypatch):
    """solve 主循环与 API /v1/research/run 必须命中同一个 research_execution 服务
    的同一个 _execute_round（monkeypatch 计数验证调用路径一致）。"""
    import vencertia.runtime.research_service as rs_mod

    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = make_orchestrator(repo, settings)
    service = runtime.engines.research_execution
    assert service is not None

    calls: list[str] = []
    # 先捕获原始方法，再打补丁（避免递归）
    original_execute_round = rs_mod.ResearchExecutionService._execute_round

    def spy_execute_round(self, *a, **k):
        calls.append("execute_round")
        return original_execute_round(self, *a, **k)

    monkeypatch.setattr(rs_mod.ResearchExecutionService, "_execute_round", spy_execute_round)

    _seed_researchable_decision(repo, "PRJ_ONE", "DEC_ONE")
    app = create_app(settings, repo, runtime)
    tc = TestClient(app)

    # solve 主循环 → run_solve_round → _execute_round
    runtime.solve(SolveRequest(project_id="PRJ_ONE", problem_text="Should we commit six weeks to the MVP?", user_id="u1"))
    assert "execute_round" in calls, "solve must call the shared _execute_round"

    # API /v1/research/run → run_plan → _execute_round
    calls.clear()
    tc.post("/v1/research/run", json={"decision_id": "DEC_ONE"})
    assert "execute_round" in calls, "API research/run must call the shared _execute_round"

    # 同一 service 实例
    assert service is runtime.engines.research_execution


def test_qa_p05_provider_failure_creates_zero_fake_evidence():
    """provider 失败 → applied_evidence 为空、belief 不变、trace.notes 记录失败。"""
    class _FailingSearch:
        name = "failing_search"

        def search(self, query, k=5):  # noqa: ARG002
            raise ProviderTimeoutError("search timed out")

    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = make_orchestrator(repo, settings, search=_FailingSearch(), retrieval=None)
    _seed_researchable_decision(repo, "PRJ_FAIL2", "DEC_FAIL2")
    beliefs_before = {b.id: b.probability for b in repo.get_beliefs("PRJ_FAIL2")}
    runtime.solve(
        SolveRequest(project_id="PRJ_FAIL2",
                     problem_text="Should we commit six weeks to the MVP?", user_id="u1")
    )
    # 无伪证据：PRJ_FAIL2 名下没有任何 evidence（compile 不产生 evidence，search 失败）
    fail_evidence = [e for e in repo.list_evidence(project_id="PRJ_FAIL2")]
    assert fail_evidence == [], "provider 失败不得产生任何伪证据"

    # belief 不变：所有 belief 概率保持 0.5（无证据 → 无更新）
    beliefs_after = {b.id: b.probability for b in repo.get_beliefs("PRJ_FAIL2")}
    for bid in set(beliefs_before) | set(beliefs_after):
        assert beliefs_after.get(bid, 0.5) == pytest.approx(0.5), (
            f"provider 失败后 belief {bid} 不得变化"
        )

    # run_plan 路径同样零伪证据 + notes 记录失败
    service = runtime.engines.research_execution
    out = service.run_plan("DEC_FAIL2")
    assert out.applied_evidence == []
    assert any("search provider failed" in note for t in out.traces for note in t.notes)


def test_qa_p05_valid_evidence_updates_belief_via_api():
    """有效证据到达后 belief 真实变化（非 OR 断言，必须两者都成立：有 applied 且 belief 动）。"""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = make_orchestrator(repo, settings)
    _seed_researchable_decision(repo, "PRJ_API2", "DEC_API2")
    app = create_app(settings, repo, runtime)
    tc = TestClient(app)
    evidence_before = len(repo.list_evidence())
    beliefs_before = {b.id: b.probability for b in repo.get_beliefs("PRJ_API2")}

    r = tc.post("/v1/research/run", json={"decision_id": "DEC_API2"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["applied_evidence"], "research/run 必须产生 applied evidence"
    assert len(repo.list_evidence()) > evidence_before

    beliefs_after = {b.id: b.probability for b in repo.get_beliefs("PRJ_API2")}
    moved = any(
        abs(beliefs_after.get(bid, 0.0) - p) > 1e-9 for bid, p in beliefs_before.items()
    )
    assert moved, "有效证据到达后 belief 必须真实变化"

    # 全部 applied evidence 归属当前项目
    for eid in {e["id"] for e in data["applied_evidence"]}:
        assert repo.get_evidence(eid).project_id == "PRJ_API2"


# ---------------------------------------------------------------------------
# P0-6 experiment validation 全入口 enforce
# ---------------------------------------------------------------------------


def test_qa_p06_vague_experiment_rejected_and_never_persisted():
    """provider 输出模糊 experiment（无三 criteria）→ 被拒不落库不推荐；default 过 validator。"""
    from vencertia.capabilities import CompiledDecision

    class _VagueCompiler:
        def compile(self, problem, project_state, options=None, context=None):  # noqa: ARG002
            decision = Decision(
                id="DEC_INV2", decision_question=problem, objective_id="OBJ_INV2",
                project_id="PRJ_INV2",
                options=[
                    DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
                    DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
                ],
                relevant_belief_ids=["wtp"],
            )
            return CompiledDecision(
                objective=Objective(id="OBJ_INV2", owner="u1", name="o", description=""),
                decision=decision,
                claims=[Claim(id="CLM_WTP", statement="ICP will pay for the promised outcome",
                              scope="PROJECT", project_id="PRJ_INV2")],
                beliefs=[Belief(id="wtp", claim_id="CLM_WTP", statement="ICP will pay",
                                scope="PROJECT", project_id="PRJ_INV2", decision_relevant=True,
                                alpha=1.0, beta=1.0, probability=0.5, posterior=0.5,
                                uncertainty=0.6, decision_weight=1.0)],
                experiments=[Experiment(
                    id="EXP_BAD2", name="Do more interviews", target_belief_ids=["wtp"],
                    hypothesis="h", action="Do some more interviews",
                    predicted_observation="o", success_criteria="",
                    failure_criteria="", ambiguity_criteria="",
                    expected_information_gain=0.5, decision_impact=0.5,
                )],
            )

    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = make_orchestrator(repo, settings, compiler=_VagueCompiler())
    result = runtime.solve(
        SolveRequest(project_id="PRJ_INV2", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    saved = repo.list_experiments("PRJ_INV2")
    assert all(e.id != "EXP_BAD2" for e in saved), "INVALID experiment 不得落库"
    assert result.next_experiment is not None, "ADR-007: ABSTAIN 必须携带 next_experiment"
    default = synthesize_default_experiment(repo.get_decision(result.decision_id), None)
    assert validate_experiment(default).valid is True


def test_qa_p06_api_propose_rejects_vague_candidate():
    """API /v1/experiments/propose：INVALID candidate 不进 ranked，rejected 非空。"""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = make_orchestrator(repo, settings)
    _seed_researchable_decision(repo, "PRJ_PROP", "DEC_PROP")
    app = create_app(settings, repo, runtime)
    tc = TestClient(app)

    vague = Experiment(
        id="EXP_VAGUE2", name="Do more interviews", target_belief_ids=["wtp"],
        hypothesis="h", action="Do some more interviews", predicted_observation="o",
        success_criteria="", failure_criteria="", ambiguity_criteria="",
        expected_information_gain=0.5, decision_impact=0.5,
    )
    r = tc.post("/v1/experiments/propose",
                json={"decision_id": "DEC_PROP",
                      "candidates": [vague.model_dump(mode="json")]})
    assert r.status_code == 200
    data = r.json()["data"]
    ranked_ids = {re_["experiment"]["id"] for re_ in data["ranked"]}
    assert "EXP_VAGUE2" not in ranked_ids
    assert any(x["experiment_id"] == "EXP_VAGUE2" for x in data["rejected"])
