"""展示层投影（独立于 runtime 引擎层）。

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
RESEARCH_STOP_STATUS_ZH = {
    "SEARCH_EXHAUSTED": "已搜索穷尽：桌面研究不再能改变判断，可停止或转入真实实验",
    "EXPERIMENT_REQUIRED": "需要真实实验：仅剩真实世界观测能降低关键不确定，做实验后再决定",
    "RESEARCH_MORE": "继续研究：边际证据价值仍高于阈值，再多查证几轮",
}
MODEL_RISK_ZH = {
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
}
CRITIQUE_FINDING_ZH = {
    "MISSING_VARIABLE": "遗漏变量",
    "HIDDEN_DEPENDENCY": "隐藏依赖",
    "REGIME_RISK": "制度/环境变化风险",
    "DOUBLE_COUNTING": "证据重复计算",
    "TAIL_RISK": "尾部风险",
    "MODEL_MISSPECIFICATION": "模型设定错误",
}

# 与 domain.calibration.classify_calibration 的默认 min_samples 保持一致。
CALIBRATION_MIN_SAMPLES: int = 20


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


def _stop_rule_phrase(stop: dict | None) -> str:
    """研究停止规则 -> 中文「何时算研究够了」描述（纯函数，永不返回空串）。"""
    if not stop:
        return "未运行停止评估（研究轮未启动，或本轮未触发停止规则）"
    status = _enum_value(stop.get("status"))
    return RESEARCH_STOP_STATUS_ZH.get(status, f"停止状态：{status}")


def experiment_voi_summary(voi: dict | None, stop: dict | None) -> dict:
    """P1-1: 实验决策价值（VOI）投影 + 停止规则投影（纯函数，不重算）。

    读取 solve() 已组装的 ``experiment_voi`` / ``research_stop`` 投影字典，
    输出：``decision_change_condition``（成功/失败/模糊三态判据）、
    ``stop_rule``（何时算研究够了的中文描述）、实验身份与降级标注。
    """
    decision_change_condition: dict = {}
    experiment: dict | None = None
    degraded = False
    if voi is not None:
        decision_change_condition = voi.get("decision_change_condition") or {}
        experiment = {
            "experiment_id": voi.get("experiment_id"),
            "name": voi.get("name"),
            "priority_score": voi.get("priority_score"),
            "decision_impact": voi.get("decision_impact"),
            "expected_information_gain": voi.get("expected_information_gain"),
        }
        decision_impact = voi.get("decision_impact")
        priority_score = voi.get("priority_score")
        # P1-1 裁决：不改排序算法，只做投影层标注——低决策影响实验明确降级提示。
        if (decision_impact is not None and float(decision_impact) <= 0) or (
            priority_score is not None and float(priority_score) == 0
        ):
            degraded = True
    note = "该实验不改变决策，已降级" if degraded else ""
    return {
        "decision_change_condition": decision_change_condition,
        "stop_rule": _stop_rule_phrase(stop),
        "experiment": experiment,
        "note": note,
    }


def personalization_summary(stakes: dict | None) -> dict:
    """P1-3: 用户风险偏好投影（读取 StakesProfile，不重算任何引擎状态）。"""
    if not stakes:
        return {"available": False, "note": "未设置风险偏好档案"}
    risk_tolerance = stakes.get("risk_tolerance")
    risk_tolerance_value = risk_tolerance if isinstance(risk_tolerance, (int, float)) else 0.5
    if risk_tolerance_value < 0.4:
        risk_level = "风险厌恶"
    elif risk_tolerance_value < 0.6:
        risk_level = "风险中性"
    else:
        risk_level = "风险偏好"
    stakes_class = stakes.get("stakes_class")
    return {
        "available": True,
        "risk_tolerance": risk_tolerance_value,
        "risk_profile_zh": risk_level,
        "max_financial_downside": stakes.get("financial_downside"),
        "reversibility": stakes.get("reversibility"),
        "time_to_recover": stakes.get("time_to_recover"),
        "stakes_class": stakes_class,
        "stakes_class_zh": STAKES_CLASS_ZH.get(_enum_value(stakes_class), ""),
        "basis": f"本建议基于你的{risk_level}偏好（风险容忍度 {risk_tolerance_value:.2f}）",
    }


def calibration_summary(profile) -> dict:
    """P1-5: 校准复盘中文解读（读取 CalibrationProfile，纯投影零重算）。

    预测校准（Brier/ECE）与决策表现（regret）拆分呈现；regret 需 outcome
    复盘结算后计算，本轮诚实标注为「本轮不展示」而非伪造数字。
    """
    from vencertia.domain.calibration import classify_calibration

    status = classify_calibration(profile.n, CALIBRATION_MIN_SAMPLES)
    sufficient = _enum_value(status) not in ("UNCALIBRATED", "LOW_SAMPLE")
    return {
        "scope": _enum_value(profile.scope),
        "scope_key": profile.scope_key,
        "n": profile.n,
        "sufficient": sufficient,
        "verdict": (
            "样本不足，结论不可用" if not sufficient
            else f"校准可用（已结算样本 {profile.n}）"
        ),
        "forecast_calibration": {
            "brier_score": profile.brier_score,
            "brier_zh": "布赖尔分数（预测与事实的均方误差，0=完美，0.25=随机猜测）",
            "ece": profile.expected_calibration_error,
            "ece_zh": "期望校准误差（置信度与实际命中率的平均绝对偏差，越低越准）",
            "mean_confidence": profile.mean_confidence,
            "empirical_rate": profile.empirical_rate,
        },
        "buckets": profile.bins,
        "decision_performance": {
            "note": "决策表现（regret）需 outcome 复盘结算后计算，本轮不展示",
        },
    }


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
        # v1.7: model-critique projection (V11 §3.8) — key always present
        "model_critique": critique_summary(result.model_critique),
        # v1.4 P1-1/P1-3: 实验 VOI + 个性化依据（键恒在，无数据时给空结构/占位文案）
        "experiment_voi": experiment_voi_summary(result.experiment_voi, result.research_stop),
        "personalization": personalization_summary(
            (result.advanced_view.stakes if result.advanced_view else None) or {}
        ),
    }


def project_advanced_view(
    belief_graph_rows: list[dict], options
) -> tuple[list[dict], list[dict]]:
    """v1.6 dependency inversion: project engine-neutral data into Chinese-labeled
    presentation structure (``relation_zh`` / ``provenance_zh``).

    The engine layer (``runtime.py``) owns only neutral data (enum values); the
    Chinese mapping constants live here in the presentation layer, which is the
    single source of copy. This removes the last ``runtime -> BELIEF_RELATION_ZH``
    / ``PROVENANCE_ZH`` import (v1.5 left this inversion for v1.6).

    Pure function: list[dict] + options in -> (belief_graph, parameter_provenance).
    """
    belief_graph: list[dict] = []
    for row in belief_graph_rows:
        r = dict(row)
        r["relation_zh"] = BELIEF_RELATION_ZH.get(r.get("relation", ""), "关系未知")
        belief_graph.append(r)

    parameter_provenance: list[dict] = []
    for option in options:
        for belief_id, param in (option.belief_parameters or {}).items():
            prov = (
                param.provenance.value
                if hasattr(param.provenance, "value")
                else str(param.provenance)
            )
            parameter_provenance.append(
                {
                    "option_id": option.id,
                    "belief_id": belief_id,
                    "value": param.value,
                    "provenance": prov,
                    "provenance_zh": PROVENANCE_ZH.get(prov, prov),
                    "status": (
                        param.status.value
                        if hasattr(param.status, "value")
                        else str(param.status)
                    ),
                    "needs_confirmation": prov == "LLM_PROPOSED",
                }
            )
    return belief_graph, parameter_provenance


def critique_summary(critique) -> dict:
    """v1.7: model-critique Chinese projection (V11 §3.8 Model Critic protocol).

    Projects the structured ``ModelCritique`` into readable Chinese copy so the
    default 5-section output surfaces "what could be wrong with the model
    itself" — not just the project assumptions. Key is always present; a
    ``None`` critique (LOW/MEDIUM stakes, critic not triggered) returns an
    explicit placeholder instead of being silently omitted.
    """
    if critique is None:
        return {"available": False, "note": "未触发模型挑战（低/中风险决策默认跳过）"}
    risk = _enum_value(critique.model_risk)
    findings_zh = [
        CRITIQUE_FINDING_ZH.get(_enum_value(f), _enum_value(f)) for f in (critique.findings or [])
    ]
    return {
        "available": True,
        "model_risk": risk,
        "model_risk_zh": MODEL_RISK_ZH.get(risk, risk),
        "model_risk_high": risk == "HIGH",
        "findings": [_enum_value(f) for f in (critique.findings or [])],
        "findings_zh": findings_zh,
        "missing_variables": list(critique.missing_variables or []),
        "hidden_dependencies": list(critique.hidden_dependencies or []),
        "regime_risks": list(critique.regime_risks or []),
        "double_counting": list(critique.double_counting or []),
        "recommendation": critique.recommendation or "",
        "note": (
            "模型整体可能错在："
            + ("；".join(findings_zh) if findings_zh else "暂未识别到结构性风险")
        ),
    }


__all__ = [
    # 13 mapping / config constants
    "PROBABILITY_BANDS",
    "ACTION_STATE_ZH",
    "DECISION_TYPE_ZH",
    "CALIBRATION_STATUS_ZH",
    "PROVENANCE_ZH",
    "BELIEF_RELATION_ZH",
    "STAKES_CLASS_ZH",
    "ENTITY_ZH",
    "PROVIDER_ERROR_ZH",
    "RESEARCH_STOP_STATUS_ZH",
    "MODEL_RISK_ZH",
    "CRITIQUE_FINDING_ZH",
    "CALIBRATION_MIN_SAMPLES",
    # 9 pure functions
    "probability_level",
    "estimate_phrase",
    "localize_error_message",
    "experiment_voi_summary",
    "personalization_summary",
    "calibration_summary",
    "solve_summary",
    "project_advanced_view",
    "critique_summary",
]
