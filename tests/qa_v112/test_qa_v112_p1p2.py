"""v1.1.2 P1/P2 adversarial verification + boundary attacks + rubber-stamp audit.

Covers CallRecorder wiring, ResearchStopRule real signals, benchmark metric
semantics, version single source, zero-skip, private-call cleanup, layer-cycle
break, facade compatibility, transaction atomicity, and legacy-data readability.
"""

from __future__ import annotations

import json
import sqlite3

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
    Project,
)
from vencertia.events.bus import EventBus
from vencertia.providers.errors import ProviderTimeoutError
from vencertia.providers.factory import with_resilience
from vencertia.providers.mock import MockProvider, MockRetrievalProvider, MockSearchProvider
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository
from vencertia.runtime import SolveOrchestrator, SolveRequest, default_engine_bundle
from vencertia.runtime.research_stop import ResearchStopRule, RoundSummary


def _make_runtime(repo, settings=None, **kw):
    settings = settings or Settings(db_dsn="sqlite:///:memory:")
    bus = EventBus(sink=repo.append_event)
    engines = default_engine_bundle(repo, settings, bus)
    return SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=kw.pop("model", MockProvider()),
        search=kw.pop("search", MockSearchProvider()),
        retrieval=kw.pop("retrieval", MockRetrievalProvider()),
        bus=bus, settings=settings, **kw,
    )


def _seed_researchable_decision(repo, project_id: str, decision_id: str) -> None:
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
            objective_id="OBJ_R", project_id=project_id,
            options=[
                DecisionOption(id="go", label="Go", belief_coefficients={"wtp": 0.8}),
                DecisionOption(id="hold", label="Hold", belief_coefficients={"wtp": 0.1}),
            ],
            relevant_belief_ids=["wtp"],
        )
    )


# ---------------------------------------------------------------------------
# P1-7 CallRecorder 接线
# ---------------------------------------------------------------------------


def test_qa_p17_solve_records_model_and_research_records_search():
    """solve 后有 model 记录（latency/success/retry_count）；research 后有 search 记录；
    记录中无 prompt / api_key 明文。"""
    settings = Settings(db_dsn="sqlite:///:memory:", provider_max_retries=1)
    repo = InMemoryRepository()
    engines = default_engine_bundle(repo, settings, EventBus(sink=repo.append_event))
    recorder = engines.call_recorder
    runtime = SolveOrchestrator(
        repo=repo, policy=engines.evidence_policy, engines=engines,
        model=with_resilience(MockProvider(), settings, recorder),
        search=with_resilience(MockSearchProvider(), settings, recorder),
        retrieval=with_resilience(MockRetrievalProvider(), settings, recorder),
        bus=EventBus(sink=repo.append_event), settings=settings,
    )
    result = runtime.solve(
        SolveRequest(project_id="PRJ_REC2", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    model_records = repo.list_call_records(kind="model")
    assert model_records, "solve 必须记录 model 调用"
    for rec in model_records:
        assert rec.latency_ms >= 0
        assert rec.success is True
        assert rec.retry_count >= 0
        payload = rec.model_dump()
        assert not payload.get("prompt")
        assert not payload.get("api_key")
        assert not any("prompt" in k.lower() or "key" in k.lower() for k in payload)

    runtime.engines.research_execution.run_plan(result.decision_id)
    search_records = repo.list_call_records(kind="search")
    assert search_records, "research 必须记录 search 调用"
    for rec in search_records:
        payload = rec.model_dump()
        assert not payload.get("prompt")
        assert not payload.get("api_key")


def test_qa_p17_failed_provider_call_recorded_with_error_type():
    """失败调用 → success=False + error_type 结构化 + 异常照常上抛。"""
    class _Failing:
        name = "failing"

        def search(self, query, k=5):  # noqa: ARG002
            raise ProviderTimeoutError("timeout")

    repo = InMemoryRepository()
    rec = default_engine_bundle(repo, Settings()).call_recorder
    wrapped = with_resilience(_Failing(), Settings(), rec)
    with pytest.raises(ProviderTimeoutError):
        wrapped.search("q")
    records = repo.list_call_records(kind="search")
    assert records and records[-1].success is False
    assert records[-1].error_type in ("TIMEOUT", "PROVIDER_TIMEOUT")


# ---------------------------------------------------------------------------
# P1-8 ResearchStopRule 真实信号
# ---------------------------------------------------------------------------


def _ev(claim_ids, authority, verification="ESTIMATED", eid="E"):
    return Evidence(
        id=eid, claim_ids=claim_ids, scope="MARKET",
        evidence_type="REVIEWED_EXTERNAL_RESEARCH", source="s",
        authority_level=authority, verification=verification,
    )


def test_qa_p18_source_quality_reflects_authority_not_constant():
    """低 authority 证据 → 低 source_quality；高 authority → 高 source_quality；
    无 applied → 0.0（不再有 0.5 占位）。"""
    rule = ResearchStopRule(Settings())
    low = _ev(["CLM_T"], "LLM_INFERENCE", eid="E_L")
    summary_low = RoundSummary(applied_evidence=[low], target_claim_ids=["CLM_T"])
    assert rule.evaluate([], [], [], ["CLM_T"], round_no=1, round_summary=summary_low).signals["source_quality"] < 0.3

    high = _ev(["CLM_T"], "PROJECT_DIRECT_BEHAVIOR", verification="VERIFIED", eid="E_H")
    summary_high = RoundSummary(applied_evidence=[high], target_claim_ids=["CLM_T"])
    assert rule.evaluate([], [], [], ["CLM_T"], round_no=1, round_summary=summary_high).signals["source_quality"] > 0.5

    summary_empty = RoundSummary(applied_evidence=[], target_claim_ids=["CLM_T"])
    assert rule.evaluate([], [], [], ["CLM_T"], round_no=1, round_summary=summary_empty).signals["source_quality"] == 0.0


def test_qa_p18_claim_coverage_is_claim_based_not_evidence_id_based():
    """claim_coverage 基于 applied_evidence.claim_ids ∩ target_claims；
    证据 id 长得像 claim id 不算数。"""
    rule = ResearchStopRule(Settings())
    real = _ev(["CLM_TARGET"], "REVIEWED_EXTERNAL_RESEARCH", eid="E_1")
    s1 = RoundSummary(applied_evidence=[real], target_claim_ids=["CLM_TARGET", "CLM_OTHER"])
    assert rule.evaluate([], [], [], ["CLM_TARGET"], round_no=1, round_summary=s1).signals["claim_coverage"] == 0.5

    fake = Evidence(id="CLM_TARGET", claim_ids=[], scope="MARKET",
                    evidence_type="REVIEWED_EXTERNAL_RESEARCH", source="y")
    s2 = RoundSummary(applied_evidence=[fake], target_claim_ids=["CLM_TARGET"])
    assert rule.evaluate([], [], [], ["CLM_TARGET"], round_no=1, round_summary=s2).signals["claim_coverage"] == 0.0


def test_qa_p18_decision_sensitivity_signal_semantics():
    """decision_sensitivity_signal：recommendation 翻转 → 1.0；无翻转 → margin 缩减比例。"""
    rule = ResearchStopRule(Settings())

    class _Res:
        def __init__(self, rec, margin):
            self.recommended_option_id = rec
            self.decision_margin = margin

    # 翻转 → 1.0
    s_flip = RoundSummary(
        decision_result_before=_Res("go", 0.3), decision_result_after=_Res("hold", 0.2),
        target_claim_ids=[],
    )
    assert rule.evaluate([], [], [], [], round_no=1, round_summary=s_flip).signals["decision_sensitivity_signal"] == 1.0

    # 未翻转，margin 0.3→0.15 → 1 - 0.15/0.3 = 0.5
    s_margin = RoundSummary(
        decision_result_before=_Res("go", 0.3), decision_result_after=_Res("go", 0.15),
        target_claim_ids=[],
    )
    assert rule.evaluate([], [], [], [], round_no=1, round_summary=s_margin).signals["decision_sensitivity_signal"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# P1-10 benchmark 语义
# ---------------------------------------------------------------------------


def test_qa_p110_l0_metrics_three_way_split():
    """L0 三分离：policy_regression（全量）/ decision_option（gold 非空）/ status。"""
    from vencertia.benchmark.metrics import compute_all

    metrics = compute_all(
        [
            {"predicted_option": "a", "gold_option": "a", "decided": True, "correct": True,
             "predicted_status": "COMMIT", "gold_status": "COMMIT", "chosen_utility": 0.8, "best_utility": 0.8},
            {"predicted_option": "b", "gold_option": "d", "decided": True, "correct": False,
             "predicted_status": "COMMIT", "gold_status": "ABSTAIN", "chosen_utility": 0.1, "best_utility": 0.9},
            {"predicted_option": "NO_DECISION", "gold_option": "NO_DECISION",
             "decided": False, "correct": True, "chosen_utility": None, "best_utility": None},
        ]
    )
    assert metrics["n_cases"] == 3
    assert metrics["policy_regression_pass_rate"] == pytest.approx(2 / 3)
    assert metrics["decision_option_accuracy"] == pytest.approx(1 / 2)
    assert metrics["decision_status_accuracy"] == pytest.approx(1 / 2)
    assert metrics["decision_accuracy"] == metrics["decision_option_accuracy"]


def test_qa_p110_l1_regret_is_none_without_utility_labels():
    """L1 无 utility → decision_regret None（不是假 0）。"""
    from vencertia.benchmark.metrics import compute_all

    metrics = compute_all(
        [
            {"predicted_option": "a", "gold_option": "a", "decided": True, "correct": True,
             "chosen_utility": None, "best_utility": None},
            {"predicted_option": "b", "gold_option": "b", "decided": True, "correct": True,
             "chosen_utility": None, "best_utility": None},
        ]
    )
    assert metrics["decision_regret"] is None


# ---------------------------------------------------------------------------
# P1-12 版本单一来源
# ---------------------------------------------------------------------------


def test_qa_p112_version_four_places_consistent():
    """__version__ / pyproject / FastAPI app.version / /health runtime_version 四处一致。"""
    import tomllib
    from pathlib import Path

    import vencertia

    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = _make_runtime(repo, settings)
    app = create_app(settings, repo, runtime)
    tc = TestClient(app)

    pyproject = tomllib.loads(
        Path(__file__).resolve().parents[2].joinpath("pyproject.toml").read_text(encoding="utf-8")
    )
    assert vencertia.__version__ == "1.6.0"
    assert pyproject["project"]["version"] == vencertia.__version__
    assert app.version == vencertia.__version__

    health = tc.get("/health").json()["data"]
    assert health["runtime_version"] == vencertia.__version__
    assert health["api_contract_version"] == "1.4"
    assert health["version"] == vencertia.__version__  # legacy alias derived from __version__
    assert health["api_version"] == "1.4.0"


# ---------------------------------------------------------------------------
# P1-11 skip 修复确认
# ---------------------------------------------------------------------------


def test_qa_p111_candidate_validation_endpoint_deterministic():
    """candidate validate 端点确定性可用（无场景依赖 skip）。"""
    from vencertia.domain import CandidateClaim

    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = _make_runtime(repo, settings)
    app = create_app(settings, repo, runtime)
    tc = TestClient(app)
    candidate = CandidateClaim(
        id="CC_QA112", statement="ICP has a severe recurring problem", scope="PROJECT",
        source_evidence_ids=["E_FIX"], extraction_confidence=0.9,
        validation_status="PENDING",
    )
    repo.save_candidate_claim(candidate)
    r = tc.post("/v1/claims/candidates/CC_QA112/validate")
    assert r.status_code == 200
    assert r.json()["data"]["validation_status"] == "VALIDATED"


# ---------------------------------------------------------------------------
# P2-14 私有调用清零（独立扫描）
# ---------------------------------------------------------------------------


def test_qa_p214_no_private_repo_calls_outside_repositories(project_root):
    """非 repository 代码零 repo._ 私有调用（含 self.repo._）。"""
    import re

    root = project_root / "src" / "vencertia"
    hits: list[str] = []
    for py in root.rglob("*.py"):
        if "repositories" in py.parts:
            continue
        text = py.read_text(encoding="utf-8")
        # 去掉注释后再匹配（避免把注释当命中）
        code = "\n".join(
            line for line in text.splitlines()
            if not line.strip().startswith("#")
        )
        if re.search(r"repo\._(list|load|store|list_all)\s*\(", code):
            hits.append(str(py.relative_to(root)))
    assert not hits, hits


# ---------------------------------------------------------------------------
# P2-15 层依赖环
# ---------------------------------------------------------------------------


def test_qa_p215_capabilities_do_not_import_runtime():
    """capabilities 模块不得 import vencertia.runtime.*（除明确依赖）。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "vencertia" / "capabilities"
    offenders: list[tuple[str, str]] = []
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("from vencertia.runtime") or stripped.startswith("import vencertia.runtime"):
                # research.py 依赖 runtime.research_stop（合理，见下）
                offenders.append((py.name, stripped))
    # research.py 允许（研究服务需 RoundSummary 等）；其余必须干净
    allowed = {py.name for py in root.rglob("*.py") if "research" in py.name}
    real_offenders = [(fname, line) for fname, line in offenders if fname not in allowed]
    assert not real_offenders, real_offenders


def test_qa_p215_capabilities_standalone_import():
    """import vencertia.capabilities 独立可用（无 runtime 导入环）。"""
    import importlib

    import vencertia.capabilities
    importlib.reload(vencertia.capabilities)
    assert vencertia.capabilities.__name__ == "vencertia.capabilities"


# ---------------------------------------------------------------------------
# P2-16 facade 兼容
# ---------------------------------------------------------------------------


def test_qa_p216_solve_result_schema_unchanged():
    """SolveResult 关键字段不变（API 兼容）；solve 后数据可读。"""
    settings = Settings(db_dsn="sqlite:///:memory:")
    repo = InMemoryRepository()
    runtime = _make_runtime(repo, settings)
    result = runtime.solve(
        SolveRequest(project_id="PRJ_FACADE", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    for field in ("decision", "decision_id", "convergence", "critical_uncertainties",
                  "next_experiment", "predictions", "rationale"):
        assert hasattr(result, field), f"SolveResult 缺字段 {field}"
    assert isinstance(result.decision_id, str)
    assert result.decision is not None
    # 持久化数据可读
    dec = repo.get_decision(result.decision_id)
    assert dec is not None


def test_qa_p216_legacy_serialized_evidence_without_project_id_readable(tmp_path):
    """v1.1.1 旧序列化数据（Evidence 无 project_id 字段）可读（optional 字段向后兼容）。"""
    repo = SQLiteRepository(path=tmp_path / "legacy.db")
    repo.save_project(Project(id="PRJ_L", user_id="u1", name="p"))
    # 手工插入一个不含 project_id 的旧 payload（模拟 v1.1.1 库）
    legacy = Evidence(id="E_LEGACY", claim_ids=["CLM_L"], scope="MARKET",
                      evidence_type="REVIEWED_EXTERNAL_RESEARCH", source="old")
    payload = legacy.model_dump(mode="json")
    payload.pop("project_id", None)
    payload.pop("company_id", None)
    repo.conn.execute(
        "INSERT INTO entities(entity_type,id,payload,version,updated_at) VALUES(?,?,?,?,?)",
        ("evidence", "E_LEGACY", json.dumps(payload), 1, "2026-01-01T00:00:00+00:00"),
    )
    repo.conn.commit()
    ev = repo.get_evidence("E_LEGACY")
    assert ev is not None
    assert ev.project_id is None  # 旧数据无 project_id → 共享 external
    # 读边界：MARKET 共享证据对任意项目可见
    repo.save_project(Project(id="PRJ_X", user_id="u1", name="x"))
    assert any(e.id == "E_LEGACY" for e in repo.list_evidence(project_id="PRJ_X"))


# ---------------------------------------------------------------------------
# P2-17 事务边界
# ---------------------------------------------------------------------------


def test_qa_p217_sqlite_no_early_commit_inside_txn(tmp_path):
    """SQLite in_transaction 内 _store 不提前 commit；外层提交后可见。"""
    db_path = tmp_path / "txn2.db"
    repo = SQLiteRepository(path=db_path)
    repo.save_project(Project(id="PRJ_1", user_id="u1", name="p"))

    other = sqlite3.connect(str(db_path))
    other.row_factory = sqlite3.Row

    observed: list[int] = []

    def batch():
        repo.save_belief(Belief(id="B1", claim_id="C1", statement="s1", scope="PROJECT", project_id="PRJ_1"))
        repo.save_belief(Belief(id="B2", claim_id="C2", statement="s2", scope="PROJECT", project_id="PRJ_1"))
        observed.append(other.execute(
            "SELECT COUNT(*) AS n FROM entities WHERE entity_type='belief'"
        ).fetchone()["n"])

    repo.in_transaction(batch)
    assert observed == [0], observed  # 事务内另一连接看不到半提交
    assert other.execute(
        "SELECT COUNT(*) AS n FROM entities WHERE entity_type='belief'"
    ).fetchone()["n"] == 2
    other.close()


def test_qa_p217_inmemory_txn_rolls_back_whole_batch():
    """InMemory in_transaction 中途失败 → 全量回滚（无半个 batch）。"""
    class _FailMidRepo:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def save_binding(self, binding, expected_version=None):  # noqa: ARG002
            raise RuntimeError("injected binding failure")

    settings = Settings(db_dsn="sqlite:///:memory:")
    inner = InMemoryRepository()
    repo = _FailMidRepo(inner)
    runtime = _make_runtime(repo, settings)
    _seed_researchable_decision(repo, "PRJ_AT2", "DEC_AT2")
    evidence_before = len(inner.list_evidence())
    with pytest.raises(RuntimeError, match="injected binding failure"):
        runtime.engines.research_execution.run_plan("DEC_AT2")
    assert len(inner.list_evidence()) == evidence_before
    assert inner.list_research_traces("DEC_AT2") == []
    beliefs = {b.id: b.probability for b in inner.get_beliefs("PRJ_AT2")}
    assert beliefs == {"wtp": 0.5}


def test_qa_p217_outcome_settlement_rolls_back_on_failure():
    """outcome settlement 中途失败 → Outcome 不存在、belief 不变。"""
    class _FailOutcomeRepo:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def save_outcome(self, outcome, expected_version=None):  # noqa: ARG002
            raise RuntimeError("injected outcome failure")

    settings = Settings(db_dsn="sqlite:///:memory:")
    inner = InMemoryRepository()
    repo = _FailOutcomeRepo(inner)
    runtime = _make_runtime(repo, settings)
    result = runtime.solve(
        SolveRequest(project_id="PRJ_OS2", problem_text="Should we commit six weeks to the MVP?",
                     user_id="u1")
    )
    decision = inner.get_decision(result.decision_id)
    inner.save_action(Action(id="ACT_OS2", project_id="PRJ_OS2", kind="EXPERIMENT",
                             decision_id=decision.id, experiment_id="EXP_OS2"))
    before = {b.id: b.probability for b in inner.get_beliefs("PRJ_OS2")}
    with pytest.raises(RuntimeError, match="injected outcome failure"):
        runtime.record_outcome("ACT_OS2", "0 paid", outcome_type="FAILURE")
    assert inner.list_outcomes(action_id="ACT_OS2") == []
    after = {b.id: b.probability for b in inner.get_beliefs("PRJ_OS2")}
    assert after == before


# ---------------------------------------------------------------------------
# 工程师测试橡皮图章审计（断言强度抽查）
# ---------------------------------------------------------------------------


def test_qa_audit_integrity_test_no_rubber_stamp():
    """审计 test_integrity_v112.py：不允许出现恒真断言（`or True` / `assert True`）。"""
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "test_integrity_v112.py"
    text = path.read_text(encoding="utf-8")
    # 已修复（发布前清理）：test_research_provider_failure_creates_no_fake_evidence
    # 的恒真式 `... or True` 已移除，替换为强断言
    # `assert repo.list_evidence() == []`（伪证据不得入库）。
    assert "or True" not in text
    assert "assert True" not in text
    # 真实断言存在（run_plan 不产生 applied evidence + 失败记录在 trace）
    assert "out.applied_evidence == []" in text
    assert "repo.list_evidence() == []" in text
