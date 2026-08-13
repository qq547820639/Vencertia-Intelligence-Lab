"""v1.3 T1 — presentation-layer Chinese phrasing + mapping constants."""

from __future__ import annotations

from vencertia.providers.errors import ProviderError, ProviderTimeoutError
from vencertia.repositories.base import EntityNotFoundError, StaleWriteError
from vencertia.runtime import (
    SolveResultAdvancedView,
    estimate_phrase,
    localize_error_message,
    probability_level,
)
from vencertia.runtime.presentation import (
    ACTION_STATE_ZH,
    BELIEF_RELATION_ZH,
    CALIBRATION_STATUS_ZH,
    DECISION_TYPE_ZH,
    ENTITY_ZH,
    PROVENANCE_ZH,
    PROVIDER_ERROR_ZH,
    STAKES_CLASS_ZH,
)


def test_calibration_status_zh_mapping():
    assert len(CALIBRATION_STATUS_ZH) == 6  # 5 real + legacy CALIBRATED alias
    assert CALIBRATION_STATUS_ZH["UNCALIBRATED"] == "未校准"
    assert CALIBRATION_STATUS_ZH["LOW_SAMPLE"] == "样本不足"
    assert CALIBRATION_STATUS_ZH["VALIDATED"] == "已验证"
    assert CALIBRATION_STATUS_ZH["CALIBRATED"] == "已校准"


def test_action_state_zh_covers_five_states():
    assert set(ACTION_STATE_ZH) == {"ACT", "TEST", "HOLD", "WAIT", "STOP"}


def test_estimate_phrase_exact_wording():
    assert (
        estimate_phrase("MODEL_SCORE", "UNCALIBRATED", 0.73)
        == "模型信念分 73（未校准，不表示真实概率）"
    )
    assert estimate_phrase("ORDINAL_SUPPORT", "LOW_SAMPLE", 0.42) == "初步估计 42（样本不足）"
    assert (
        estimate_phrase("CALIBRATED_PROBABILITY", "DOMAIN_CALIBRATED", 0.73)
        == "校准后约 73%"
    )
    assert estimate_phrase("CALIBRATED_PROBABILITY", "USER_CALIBRATED", 0.5) == "校准后约 50%"
    assert estimate_phrase("CALIBRATED_PROBABILITY", "VALIDATED", 0.9) == "校准后约 90%"
    assert estimate_phrase("CALIBRATED_PROBABILITY", "CALIBRATED", 0.6) == "校准后约 60%"
    # UNCALIBRATED 文案用"信念分"作名词（而非"概率"），并明确不表示真实概率。
    phrase = estimate_phrase("MODEL_SCORE", "UNCALIBRATED", 0.73)
    assert "信念分" in phrase
    assert "真实发生概率" not in phrase


def test_probability_level_bands():
    assert probability_level(0.39) == "Low"
    assert probability_level(0.40) == "Moderate"  # 边界闭左
    assert probability_level(0.60) == "Moderate"
    assert probability_level(0.61) == "High"
    assert probability_level(0.0) == "Low"
    assert probability_level(1.0) == "High"


def test_localize_error_message():
    assert localize_error_message(EntityNotFoundError("decision", "DEC_X")) == "未找到决策：DEC_X"
    assert (
        localize_error_message(StaleWriteError("belief", "BLF_X", 3))
        == "数据已过期（信念:BLF_X），请刷新后重试"
    )
    assert localize_error_message(ProviderTimeoutError("x")) == "提供方超时"
    assert localize_error_message(ProviderError("boom")) == "提供方错误"
    assert localize_error_message(ValueError("bad input")) == "参数错误：bad input"


def test_mapping_constants_present():
    assert PROVENANCE_ZH["USER_DEFINED"] == "由你设定"
    assert PROVENANCE_ZH["LLM_PROPOSED"] == "模型建议，未经你确认"
    assert PROVENANCE_ZH["UNKNOWN"] == "来源未知"
    assert BELIEF_RELATION_ZH["CAUSES"] == "因果关系"
    assert BELIEF_RELATION_ZH["UNKNOWN_RELATIONSHIP"] == "关系未知"
    assert DECISION_TYPE_ZH["ABSTAIN"] == "暂不决策"
    assert STAKES_CLASS_ZH["HIGH"] == "高风险（不可逆，需谨慎）"
    assert ENTITY_ZH["decision"] == "决策"
    assert PROVIDER_ERROR_ZH["TIMEOUT"] == "提供方超时"


def test_runtime_exports_advanced_view_and_phrasing():
    # T1 export contract: all importable from vencertia.runtime.
    assert SolveResultAdvancedView is not None
    assert callable(estimate_phrase)
    assert callable(probability_level)
    assert callable(localize_error_message)


def test_project_advanced_view_chinese_labels():
    """v1.6: project_advanced_view is the single source of relation_zh/provenance_zh."""
    from vencertia.domain.decision import DecisionOption
    from vencertia.domain.model_parameter import ApprovalStatus, ModelParameter, ProvenanceType
    from vencertia.presentation import project_advanced_view

    graph, prov = project_advanced_view(
        [{"id": "BE_1", "relation": "CAUSES"}, {"id": "BE_2", "relation": "UNKNOWN_RELATIONSHIP"}],
        [
            DecisionOption(
                id="opt1", label="A",
                belief_parameters={
                    "b1": ModelParameter(value=0.7, provenance=ProvenanceType.USER_DEFINED, status=ApprovalStatus.APPROVED),
                    "b2": ModelParameter(value=0.3, provenance=ProvenanceType.LLM_PROPOSED, status=ApprovalStatus.PROPOSED),
                },
            )
        ],
    )
    assert graph[0]["relation_zh"] == "因果关系"
    assert graph[1]["relation_zh"] == "关系未知"
    by_belief = {p["belief_id"]: p for p in prov}
    assert by_belief["b1"]["provenance_zh"] == "由你设定"
    assert by_belief["b1"]["needs_confirmation"] is False
    assert by_belief["b2"]["provenance_zh"] == "模型建议，未经你确认"
    assert by_belief["b2"]["needs_confirmation"] is True
