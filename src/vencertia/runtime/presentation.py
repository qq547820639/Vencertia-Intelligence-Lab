"""Presentation-layer phrasing (v1.3 UX projection).

All Chinese copy lives HERE — a single import surface for the API and CLI.
Every template is a pure function (scalar/enum/computed-object in, str/dict
out) with zero side effects so it can be unit-tested in isolation.

The domain enums stay in ``vencertia.domain``; this module only adds the
presentation-layer Chinese mappings and phrasing (ADR: no new enums, no
``extra="forbid"`` ripple).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from vencertia.runtime.runtime import SolveResultV11

# ---- probability level band thresholds (static constant, design ruling #4) ----
PROBABILITY_BANDS: dict[str, float] = {"low": 0.40, "high": 0.60}

# ---- enum -> Chinese mapping constants (single source of copy) ----
ACTION_STATE_ZH = {
    "ACT": "行动",
    "TEST": "试验验证",
    "HOLD": "暂缓",
    "WAIT": "等待",
    "STOP": "停止",
}
DECISION_TYPE_ZH = {
    "GO": "推进",
    "CONDITIONAL_GO": "有条件推进",
    "SELECT_OPTION": "选择方案",
    "HOLD": "暂缓",
    "PIVOT": "转向",
    "KILL": "终止",
    "ABSTAIN": "暂不决策",
}
CALIBRATION_STATUS_ZH = {
    "UNCALIBRATED": "未校准",
    "LOW_SAMPLE": "样本不足",
    "DOMAIN_CALIBRATED": "领域校准",
    "USER_CALIBRATED": "用户校准",
    "VALIDATED": "已验证",
    "CALIBRATED": "已校准",  # legacy alias
}
PROVENANCE_ZH = {
    "USER_DEFINED": "由你设定",
    "OBSERVED": "由观察得到",
    "DOMAIN_DEFAULT": "领域默认值",
    "EMPIRICALLY_ESTIMATED": "经验估计",
    "LLM_PROPOSED": "模型建议，未经你确认",
    "UNKNOWN": "来源未知",
}
BELIEF_RELATION_ZH = {
    "CAUSES": "因果关系",
    "DEPENDS_ON": "依赖关系",
    "MEDIATES": "中介作用",
    "MODERATES": "调节作用",
    "SHARES_LATENT_FACTOR": "共享潜在因子",
    "SHARED_SIGNAL": "共享信号",
    "REDUNDANT_WITH": "冗余",
    "MUTUALLY_EXCLUSIVE": "互斥",
    "UNKNOWN_RELATIONSHIP": "关系未知",
}
STAKES_CLASS_ZH = {
    "HIGH": "高风险（不可逆，需谨慎）",
    "MEDIUM": "中等风险",
    "LOW": "低风险（可逆）",
}
ENTITY_ZH = {
    "decision": "决策",
    "project": "项目",
    "evidence": "证据",
    "experiment": "实验",
    "belief": "信念",
    "prediction": "预测",
    "claim": "声明",
    "candidate_claim": "候选声明",
    "decision_trace": "决策追踪",
    "decision_sensitivity": "决策敏感度",
    "outcome": "结果",
}
PROVIDER_ERROR_ZH = {
    "TIMEOUT": "提供方超时",
    "RATE_LIMIT": "提供方限流",
    "UNAVAILABLE": "提供方不可用",
    "INVALID_JSON": "提供方返回格式错误",
    "SCHEMA_MISMATCH": "提供方返回结构不匹配",
    "EMPTY_RESULT": "提供方返回空结果",
    "PARTIAL_RESULT": "提供方返回部分结果",
    "PROVIDER_ERROR": "提供方错误",
}


def _enum_value(x) -> str:
    """enum or plain string -> canonical value (runtime values are strings)."""
    return x.value if hasattr(x, "value") else str(x)


def _pct_int(value: float) -> str:
    """0-1 -> integer percentage string (without the ``%`` sign)."""
    return f"{max(0.0, min(1.0, value)) * 100:.0f}"


def probability_level(value: float) -> str:
    """v1.3 ruling #3: default output uses a band (Low/Moderate/High)."""
    v = max(0.0, min(1.0, value))
    if v < PROBABILITY_BANDS["low"]:
        return "Low"
    if v > PROBABILITY_BANDS["high"]:
        return "High"
    return "Moderate"


def estimate_phrase(estimate_type, calibration_status, value: float) -> str:
    """v1.3 P0-2: probability-credibility phrasing template (pure function).

    ``estimate_type`` is reserved for a future MODEL_SCORE vs
    CALIBRATED_PROBABILITY noun switch; v1.3 phrasing is driven solely by
    ``calibration_status``.
    """
    _ = estimate_type  # reserved, no branch in v1.3
    st = _enum_value(calibration_status)
    v = _pct_int(value)
    if st == "UNCALIBRATED":
        return f"模型信念分 {v}（未校准，不表示真实概率）"
    if st == "LOW_SAMPLE":
        return f"初步估计 {v}（样本不足）"
    # DOMAIN_CALIBRATED / USER_CALIBRATED / VALIDATED / CALIBRATED (legacy)
    return f"校准后约 {v}%"


def localize_error_message(exc: Exception) -> str:
    """v1.3 P0-5: exception -> readable Chinese copy (HTTP status unchanged)."""
    from vencertia.providers.errors import ProviderError
    from vencertia.repositories.base import EntityNotFoundError, StaleWriteError

    if isinstance(exc, EntityNotFoundError):
        return f"未找到{ENTITY_ZH.get(exc.entity_type, exc.entity_type)}：{exc.entity_id}"
    if isinstance(exc, StaleWriteError):
        return f"数据已过期（{ENTITY_ZH.get(exc.entity_type, exc.entity_type)}:{exc.entity_id}），请刷新后重试"
    if isinstance(exc, ProviderError):
        return PROVIDER_ERROR_ZH.get(getattr(exc, "error_type", ""), "提供方错误")
    if isinstance(exc, ValueError):
        return f"参数错误：{exc}"
    return str(exc)


def solve_summary(result: SolveResultV11) -> dict:
    """v1.3 P0-1: default 5-section output contract (progressive disclosure).

    Pure function reading only the already-computed ``SolveResultV11`` material
    (never recomputes engine state):

      段1 当前判断   <- action_state / decision.status / decision.confidence
      段2 为什么     <- evidence_used count + engine conclusion
      段3 最大未知   <- critical_uncertainties[0]
      段4 下一步     <- next_experiment or abstain_exit_condition
      段5 什么会改变 <- what_could_change_my_mind
      ABSTAIN 四要素 <- abstain_exit_condition / next_experiment /
                        stop_condition + success/failure_criteria / stakes
      透明度段       <- advanced_view.belief_graph / parameter_provenance
    """
    decision = result.decision
    action = _enum_value(result.action_state) if result.action_state else "HOLD"
    status = _enum_value(decision.status)
    stakes_class = _enum_value(decision.stakes_class)
    mode = _enum_value(result.mode) if result.mode else None

    # 段1 当前判断
    current_judgment = action
    current_judgment_zh = ACTION_STATE_ZH.get(action, action)
    confidence_phrase = (
        estimate_phrase("MODEL_SCORE", "UNCALIBRATED", decision.confidence)
        if decision.confidence is not None
        else "置信度未知"
    )

    # 段2 为什么
    evidence_count = len(result.evidence_used or [])
    rationale = (
        f"判断基于 {evidence_count} 条已采信证据与确定性效用引擎；"
        f"引擎结论为「{DECISION_TYPE_ZH.get(status, status)}」（{current_judgment_zh}）。"
    )

    # 段3 最大未知
    top = result.critical_uncertainties[0] if result.critical_uncertainties else None
    biggest_unknown = (
        f"关键未知：{top.statement}（belief {top.belief_id}，不确定性 {top.uncertainty:.0%}）"
        if top
        else "暂无关键未知项"
    )

    # 段4 下一步（mode 措辞切换：EXPLORE=最小验证动作 / OPERATE=下一步行动 / None=中性）
    step_noun = {"EXPLORE": "最小验证动作", "OPERATE": "下一步行动"}.get(mode, "下一步")
    if result.next_experiment is not None:
        exp = result.next_experiment.experiment
        next_step = f"{step_noun}：{exp.name}（{exp.action or '见实验详情'}，成本 {exp.cost:.1f}）"
    elif status == "ABSTAIN":
        next_step = f"{step_noun}：{decision.abstain_exit_condition or '补充决策改变型证据'}"
    else:
        next_step = "无待办实验（判断已收敛，可执行）"

    # 段5 什么会改变判断
    change_condition = list(result.what_could_change_my_mind or [])
    if not change_condition:
        change_condition = ["当前无邻近翻转阈值（判断对信念扰动稳健）"]

    # P0-3 ABSTAIN 四要素（仅 ABSTAIN 分支填充，否则空串/未设置，绝不省略键）
    is_abstain = status == "ABSTAIN"
    why_not_decide = (
        f"暂不决策：{decision.abstain_exit_condition or '证据不足以区分选项'}"
        if is_abstain
        else ""
    )
    lowest_cost_next_step = next_step if is_abstain else ""
    stop_condition = ""
    if is_abstain:
        parts = [
            p for p in (result.stop_condition, result.success_criteria, result.failure_criteria) if p
        ]
        stop_condition = "；".join(parts) if parts else "未设置停止条件"
    deadline = "未设置"  # StakesProfile has no deadline field -> always "未设置"
    stakes_class_zh = STAKES_CLASS_ZH.get(stakes_class, stakes_class)

    # P0-4 透明度段（T3 填数据源；此处防御读取）
    adv = result.advanced_view
    belief_deps: list[dict] = []
    if adv is not None and adv.belief_graph:
        belief_deps = [
            {
                "source_belief_id": e.get("source_belief_id"),
                "target_belief_id": e.get("target_belief_id"),
                "relation": e.get("relation"),
                "relation_zh": BELIEF_RELATION_ZH.get(e.get("relation", ""), "关系未知"),
            }
            for e in adv.belief_graph
        ]
    provenance = getattr(adv, "parameter_provenance", []) or []  # T3 field, defensive read

    return {
        "view": "summary",
        "current_judgment": current_judgment,  # ∈ ActionState five states
        "current_judgment_zh": current_judgment_zh,
        "decision_status": status,
        "confidence_phrase": confidence_phrase,
        "rationale": rationale,
        "evidence_count": evidence_count,
        "biggest_unknown": biggest_unknown,
        "next_step": next_step,
        "change_condition": change_condition,
        # ABSTAIN 四要素
        "why_not_decide": why_not_decide,
        "lowest_cost_next_step": lowest_cost_next_step,
        "stop_condition": stop_condition,
        "deadline": deadline,
        "stakes_class": stakes_class,
        "stakes_class_zh": stakes_class_zh,
        # 透明度
        "belief_dependencies": belief_deps,
        "provenance_summary": provenance,
    }
