"""V11 专家提示词资产迁移（v2.0 skill 实现）。

每个 skill 对应 legacy/agent_v11 的一个专家角色：
  market_opportunity      ← Vencertia_Market_Opportunity_V11
  financial_model         ← Vencertia_Financial_and_Business_Model_V11
  plan_narrative          ← Vencertia_Business_Plan_Architect_V11
  founder_diagnosis       ← Vencertia_Founder_Diagnosis_V11
  execution_strategy      ← Vencertia_Execution_Strategy_V11 / Next_Action_Planner

经验以提示词模板形式承载（prompt 为一等资产，版本号 = 资产谱系 v11.0）；
输出走契约 + 引用校验。真实 LLM 模式下调用 model.generate_structured；
mock 模式用确定性模板回退，产出引用真实上下文的诚实内容（deterministic=True），
全链路离线可验证 —— 与整个运行时的"离线诚实"一致。
"""

from __future__ import annotations

from vencertia.providers.models import ModelProvider
from vencertia.skills.base import SkillCandidate, SkillMetadata

# ---------------------------------------------------------------------------
# prompt templates（经验资产本体；占位符为 {task}/{context_json}）
# ---------------------------------------------------------------------------

MARKET_PROMPT = (
    "你是 Vencertia 市场机会专家（V11 Market Opportunity）。基于给定的决策上下文"
    "撰写市场机会叙事：每个论点必须引用上下文中的 claim_id 作为出处；"
    "任何数字必须携带 source_claim_id，禁止编造市场规模或增长率。"
    "输出 JSON：{thesis, items:[{claim_id, statement, evidence_summary, numbers:[{label, value, source_claim_id}]}]}"
)

FINANCIAL_PROMPT = (
    "你是 Vencertia 财务与商业模式专家（V11 Financial & Business Model）。"
    "基于上下文中的假设登记表推导单位经济学与里程碑：每条假设必须引用"
    "source_claim_id（有出处），数据不足的假设明确标注『待验证』，不得编造。"
    "输出 JSON：{unit_economics, assumptions:[{label, value, source_claim_id, note}], milestones:[str]}"
)

PLAN_PROMPT = (
    "你是 Vencertia 商业计划架构师（V11 Business Plan Architect）。"
    "基于决策证据撰写计划叙事章节：每个论点引用 source_claim_id；"
    "证据不足处诚实说明，不替用户编造事实。"
    "输出 JSON：{sections:[{title, body, source_claim_id}]}"
)

FOUNDER_PROMPT = (
    "你是 Vencertia 创始人诊断专家（V11 Founder Diagnosis）。"
    "基于上下文观察创始人风险信号：每条信号引用 source_claim_id（无证据则留空并注明观察不足）。"
    "输出 JSON：{thesis, signals:[{label, observation, source_claim_id}]}"
)

EXECUTION_PROMPT = (
    "你是 Vencertia 执行策略专家（V11 Execution Strategy / Next Action Planner）。"
    "基于决策的下一步实验与里程碑给出执行步骤：每步引用 source_claim_id 说明依据。"
    "输出 JSON：{steps:[{step, rationale, source_claim_id}]}"
)


class _NarrativeSkillBase:
    """Shared plumbing: mock template + optional real-model path."""

    contract = ""

    def __init__(self, model: ModelProvider | None = None) -> None:
        self.model = model
        self._use_model = model is not None and getattr(model, "name", "") not in ("mock",)

    def _candidate(self, name: str, version: str, payload: dict, deterministic: bool) -> SkillCandidate:
        return SkillCandidate(
            skill=name, version=version, contract=self.contract,
            payload=payload, deterministic=deterministic,
        )

    def _via_model(self, prompt: str, context: dict) -> dict | None:
        """Real LLM path (config-gated); returns None when unavailable."""
        if not self._use_model:
            return None
        try:
            return self.model.generate_structured(prompt, {"kind": self.contract}, context)
        except Exception:  # degrade: deterministic template takes over (never blocks)
            return None


class MarketOpportunitySkill(_NarrativeSkillBase):
    contract = "MarketOpportunityContract"

    def run(self, context: dict) -> SkillCandidate:
        raw = self._via_model(MARKET_PROMPT, context)
        if raw:
            return self._candidate("market_opportunity", "v11.0", raw, deterministic=False)
        beliefs = [
            b for b in context.get("beliefs", [])
            if b.get("scope") in ("MARKET", "WORLD") or "market" in (b.get("statement") or "").lower()
        ]
        payload = {
            "thesis": "基于已采信证据的市场机会判断（确定性模板，未接真实 LLM）",
            "items": [
                {
                    "claim_id": b.get("claim_id", ""),
                    "statement": b.get("statement", ""),
                    "evidence_summary": f"证据 {b.get('evidence_count', 0)} 条，概率 {b.get('probability')}",
                    "numbers": [],
                }
                for b in beliefs[:5]
            ],
        }
        return self._candidate("market_opportunity", "v11.0", payload, deterministic=True)


class FinancialModelSkill(_NarrativeSkillBase):
    contract = "FinancialModelContract"

    def run(self, context: dict) -> SkillCandidate:
        raw = self._via_model(FINANCIAL_PROMPT, context)
        if raw:
            return self._candidate("financial_model", "v11.0", raw, deterministic=False)
        register = context.get("assumptions") or []
        payload = {
            "unit_economics": "确定性骨架未含收入假设；单位经济学需由假设登记表中的支付意愿证据推导（待验证）。",
            "assumptions": [
                {
                    "label": a.get("statement", "")[:60],
                    "value": f"概率 {a.get('probability')}（不确定性 {a.get('uncertainty')}）",
                    "source_claim_id": a.get("claim_id", ""),
                    "note": "来自假设登记表；未确认为财务事实",
                }
                for a in register[:6]
            ],
            "milestones": [
                f"验证假设「{a.get('statement', '')[:40]}」" for a in register[:3]
            ],
        }
        return self._candidate("financial_model", "v11.0", payload, deterministic=True)


class PlanNarrativeSkill(_NarrativeSkillBase):
    contract = "PlanNarrativeContract"

    def run(self, context: dict) -> SkillCandidate:
        raw = self._via_model(PLAN_PROMPT, context)
        if raw:
            return self._candidate("plan_narrative", "v11.0", raw, deterministic=False)
        decision = context.get("decision") or {}
        experiments = context.get("experiments") or []
        first_claim = (context.get("claim_ids") or [None])[0] or ""
        sections = [
            {
                "title": "计划叙事",
                "body": (
                    f"决策问题：{decision.get('decision_question', '—')}；"
                    f"当前判断：{decision.get('current_recommendation') or '暂不决策（ABSTAIN）'}。"
                    "本叙事由确定性模板生成，未接真实 LLM。"
                ),
                "source_claim_id": first_claim,
            }
        ]
        for e in experiments[:2]:
            sections.append(
                {
                    "title": f"里程碑实验：{e.get('name')}",
                    "body": (
                        f"成功判据：{e.get('success_criteria') or '—'}；"
                        f"失败判据：{e.get('failure_criteria') or '—'}"
                    ),
                    "source_claim_id": first_claim,
                }
            )
        return self._candidate(
            "plan_narrative", "v11.0", {"sections": sections}, deterministic=True
        )


class FounderDiagnosisSkill(_NarrativeSkillBase):
    contract = "FounderDiagnosisContract"

    def run(self, context: dict) -> SkillCandidate:
        raw = self._via_model(FOUNDER_PROMPT, context)
        if raw:
            return self._candidate("founder_diagnosis", "v11.0", raw, deterministic=False)
        payload = {
            "thesis": "本上下文未包含创始人画像数据；诊断不适用（诚实 N/A，确定性模板）。",
            "signals": [],
        }
        return self._candidate("founder_diagnosis", "v11.0", payload, deterministic=True)


class ExecutionStrategySkill(_NarrativeSkillBase):
    contract = "ExecutionStrategyContract"

    def run(self, context: dict) -> SkillCandidate:
        raw = self._via_model(EXECUTION_PROMPT, context)
        if raw:
            return self._candidate("execution_strategy", "v11.0", raw, deterministic=False)
        experiments = context.get("experiments") or []
        first_claim = (context.get("claim_ids") or [None])[0] or ""
        steps = []
        for e in experiments[:3]:
            steps.append(
                {
                    "step": f"执行实验「{e.get('name')}」（{e.get('action') or '见详情'}）",
                    "rationale": "由决策引擎按信息价值排序推荐（确定性模板）",
                    "source_claim_id": first_claim,
                }
            )
        if not steps:
            steps.append(
                {
                    "step": "判断已收敛，进入执行阶段",
                    "rationale": "引擎未给出待办实验",
                    "source_claim_id": first_claim,
                }
            )
        return self._candidate(
            "execution_strategy", "v11.0", {"steps": steps}, deterministic=True
        )


def build_biz_skill_registry(model: ModelProvider | None = None):
    """装配层：注册全部 V11 迁移 skill（与 provider 组合根同源）。"""
    from vencertia.skills.base import SkillRegistry

    registry = SkillRegistry()
    specs = [
        (MarketOpportunitySkill, "market_opportunity", "bp", "Vencertia_Market_Opportunity_V11_v0.1.docx"),
        (FinancialModelSkill, "financial_model", "bp", "Vencertia_Financial_and_Business_Model_V11_v0.1.docx"),
        (PlanNarrativeSkill, "plan_narrative", "bp", "Vencertia_Business_Plan_Architect_V11_v0.1.docx"),
        (FounderDiagnosisSkill, "founder_diagnosis", "idea", "Vencertia_Founder_Diagnosis_V11_v0.1.docx"),
        (ExecutionStrategySkill, "execution_strategy", "execution", "Vencertia_Execution_Strategy_V11_v0.1.docx"),
    ]
    for skill_cls, name, stage, source in specs:
        registry.register(
            skill_cls(model=model),
            SkillMetadata(
                name=name,
                version="v11.0",
                v11_source=source,
                description=f"legacy V11 专家角色 {name} 的版本化提示词资产",
                contract=skill_cls.contract,
                stage=stage,
            ),
        )
    return registry
