"""v1.7 — model-critique Chinese projection (V11 §3.8 Model Critic protocol)."""

from __future__ import annotations

from vencertia.domain.critic import CritiqueFindingType, ModelCritique, ModelRisk
from vencertia.presentation import (
    CRITIQUE_FINDING_ZH,
    MODEL_RISK_ZH,
    critique_summary,
    solve_summary,
)
from vencertia.runtime import SolveRequest


def _critique(**kw) -> ModelCritique:
    defaults = dict(
        id="MCR_TEST",
        decision_id="DEC_TEST",
        model_risk=ModelRisk.HIGH,
        findings=[CritiqueFindingType.MISSING_VARIABLE, CritiqueFindingType.DOUBLE_COUNTING],
        missing_variables=["监管政策变化"],
        double_counting=["同一付款同时支持 WTP 与 Demand"],
        recommendation="重新审视模型是否遗漏监管变量",
    )
    defaults.update(kw)
    return ModelCritique(**defaults)


def test_critique_summary_none_placeholder():
    s = critique_summary(None)
    assert s["available"] is False
    # v2.0.1: honest placeholder (covers both "gate not triggered" and
    # "no real critique provider wired") — never a canned verdict.
    assert "模型自检不可用" in s["note"]


def test_critique_summary_projection():
    s = critique_summary(_critique())
    assert s["available"] is True
    assert s["model_risk"] == "HIGH"
    assert s["model_risk_zh"] == "高"
    assert s["model_risk_high"] is True
    assert s["findings_zh"] == ["遗漏变量", "证据重复计算"]
    assert s["missing_variables"] == ["监管政策变化"]
    assert s["double_counting"] == ["同一付款同时支持 WTP 与 Demand"]
    assert s["recommendation"] == "重新审视模型是否遗漏监管变量"
    assert "模型整体可能错在" in s["note"]


def test_critique_summary_low_risk_not_high():
    s = critique_summary(_critique(model_risk=ModelRisk.LOW, findings=[]))
    assert s["model_risk_zh"] == "低"
    assert s["model_risk_high"] is False
    assert s["findings_zh"] == []
    assert "暂未识别到结构性风险" in s["note"]


def test_critique_zh_mapping_constants():
    assert MODEL_RISK_ZH["HIGH"] == "高"
    assert CRITIQUE_FINDING_ZH["MODEL_MISSPECIFICATION"] == "模型设定错误"
    assert CRITIQUE_FINDING_ZH["REGIME_RISK"] == "制度/环境变化风险"


def test_solve_summary_model_critique_key_present(orchestrator):
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_CRIT", problem_text="Should we commit?", user_id="u1")
    )
    s = solve_summary(result)
    # key always present; default (no HIGH stakes) does not trigger the critic
    assert "model_critique" in s
    assert s["model_critique"]["available"] is False
