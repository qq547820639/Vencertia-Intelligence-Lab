"""v1.4 T1 — P1-1 实验 VOI + P1-3 个性化 + P1-5 校准复盘（展示层投影）。

全部为纯函数投影断言：只读取 SolveResultV11 / CalibrationProfile 已算字段，
不重算引擎状态（延续 v1.3 ``solve_summary`` 的纯函数约定）。
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from tests.conftest import FIVE_KEYS
from vencertia.cli import app
from vencertia.domain import CalibrationProfile, ConvergenceReport, DecisionResult
from vencertia.runtime import SolveRequest, SolveResultV11
from vencertia.runtime.presentation import (
    calibration_summary,
    experiment_voi_summary,
    personalization_summary,
    solve_summary,
)


def test_experiment_voi_field_defaults():
    """P1-1：新字段可选且默认 None，旧构造不破坏。"""
    result = SolveResultV11(
        decision=DecisionResult(
            decision_id="DEC_1",
            status="ABSTAIN",
            recommended_option_id=None,
            confidence=0.5,
            decision_margin=0.1,
        ),
        decision_id="DEC_1",
        convergence=ConvergenceReport(decision_id="DEC_1"),
    )
    assert result.experiment_voi is None
    assert result.research_stop is None


def test_solve_projects_experiment_voi_and_research_stop(orchestrator):
    """P1-1：ABSTAIN solve() 后投影 decision_change_condition 与 stop signals。"""
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_V14_1",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    assert result.decision.status == "ABSTAIN"
    assert result.experiment_voi is not None
    assert result.research_stop is not None
    dcc = result.experiment_voi["decision_change_condition"]
    assert set(dcc) == {"success", "failure", "ambiguity"}
    assert all(dcc[k] for k in dcc)
    assert result.research_stop["status"] in {
        "SEARCH_EXHAUSTED",
        "EXPERIMENT_REQUIRED",
        "RESEARCH_MORE",
    }
    assert "decision_sensitivity_signal" in result.research_stop["signals"]


def test_solve_summary_experiment_voi_section(orchestrator):
    """P1-1：solve_summary 的 experiment_voi 段含 decision_change_condition 与 stop_rule。"""
    result = orchestrator.solve(
        SolveRequest(
            project_id="PRJ_V14_2",
            problem_text="Should we commit six weeks to the MVP?",
            user_id="u1",
        )
    )
    s = solve_summary(result)
    section = s["experiment_voi"]
    assert set(section) >= {"decision_change_condition", "stop_rule"}
    assert isinstance(section["stop_rule"], str) and section["stop_rule"]


def test_experiment_voi_degraded_annotation():
    """P1-1：decision_impact<=0 或 priority_score==0 的实验标「不改变决策/已降级」。"""
    voi = {
        "experiment_id": "EXP_D",
        "name": "degraded experiment",
        "priority_score": 0.0,
        "decision_impact": 0.0,
        "expected_information_gain": 0.5,
        "decision_change_condition": {"success": "s", "failure": "f", "ambiguity": "a"},
    }
    out = experiment_voi_summary(voi, None)
    assert "不改变决策" in out["note"] or "已降级" in out["note"]


def test_personalization_summary_available():
    """P1-3：有 risk_tolerance 时 available=True 且 basis 含「风险厌恶」。"""
    s = personalization_summary(
        {
            "risk_tolerance": 0.3,
            "financial_downside": 100.0,
            "reversibility": 0.2,
            "time_to_recover": 6.0,
            "stakes_class": "HIGH",
        }
    )
    assert s["available"] is True
    assert "风险厌恶" in s["basis"]
    assert s["stakes_class"] == "HIGH"
    assert s["stakes_class_zh"] == "高风险（不可逆，需谨慎）"


def test_personalization_summary_unavailable():
    """P1-3：无 stakes 档案时 available=False。"""
    s = personalization_summary(None)
    assert s["available"] is False
    s_empty = personalization_summary({})
    assert s_empty["available"] is False


def test_solve_summary_zero_regression(orchestrator):
    """v1.3 既有 FIVE_KEYS 断言继续成立（新键纯追加）。"""
    result = orchestrator.solve(
        SolveRequest(project_id="PRJ_V14_3", problem_text="Should we commit?", user_id="u1")
    )
    s = solve_summary(result)
    assert set(s) >= FIVE_KEYS


def test_calibration_summary_insufficient_samples():
    """P1-5：样本不足 → verdict 固定文案、sufficient=False。"""
    s = calibration_summary(CalibrationProfile(id="CAL_X", n=3))
    assert s["verdict"] == "样本不足，结论不可用"
    assert s["sufficient"] is False


def test_calibration_summary_sufficient_samples():
    """P1-5：样本充足 → sufficient=True 且 verdict 含「校准可用」。"""
    s = calibration_summary(CalibrationProfile(id="CAL_X", n=50))
    assert s["sufficient"] is True
    assert "校准可用" in s["verdict"]


def test_calibration_summary_metric_split():
    """P1-5：指标拆分 forecast_calibration / decision_performance + 分桶明细键。"""
    profile = CalibrationProfile(
        id="CAL_X",
        n=50,
        brier_score=0.2,
        expected_calibration_error=0.1,
        mean_confidence=0.8,
        empirical_rate=0.7,
        bins=[
            {
                "lo": 0.0,
                "hi": 0.1,
                "n": 5,
                "mean_confidence": 0.05,
                "empirical_rate": 0.1,
                "gap": -0.05,
            }
        ],
    )
    s = calibration_summary(profile)
    assert set(s) >= {"forecast_calibration", "decision_performance"}
    assert isinstance(s["buckets"], list)
    for bucket in s["buckets"]:
        assert set(bucket) >= {"lo", "hi", "mean_confidence", "empirical_rate", "gap"}


def test_cli_calibration_report_chinese(tmp_path):
    """P1-5：CLI calibration report 输出中文 verdict / brier_zh / ece_zh。"""
    runner = CliRunner()
    r = runner.invoke(app, ["calibration", "report", "--db", str(tmp_path / "cal.db")])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert ("样本不足" in payload["verdict"]) or ("校准可用" in payload["verdict"])
    assert "布赖尔分数" in payload["forecast_calibration"]["brier_zh"]
    assert "期望校准误差" in payload["forecast_calibration"]["ece_zh"]
