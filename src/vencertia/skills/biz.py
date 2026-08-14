"""V11 专家提示词资产迁移（v2.0 skill 实现）。

每个 skill 对应 legacy/agent_v11 的一个专家角色：
  market_opportunity      ← Vencertia_Market_Opportunity_V11
  financial_model         ← Vencertia_Financial_and_Business_Model_V11
  plan_narrative          ← Vencertia_Business_Plan_Architect_V11
  founder_diagnosis       ← Vencertia_Founder_Diagnosis_V11
  execution_strategy      ← Vencertia_Execution_Strategy_V11 / Next_Action_Planner

经验以提示词模板形式承载（prompt 为一等资产，版本号 = 资产谱系 v11.0）；
输出走契约 + 引用校验。skill 永远调用配置的 AI 模型（真实路径）；
模型未配置或调用失败 ⇒ 该 skill 在编排层被标记 REJECTED（诚实降级），
绝不生成模板叙事冒充 AI 产出（v2.0.1 产品裁决：演示模式仅存在于测试）。
"""

from __future__ import annotations

from vencertia.providers.errors import ProviderUnavailableError
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
    """Shared plumbing: every skill calls the CONFIGURED AI model.

    No template fallback: a missing/failed model means the orchestration layer
    marks this skill REJECTED (honest degradation), it never fabricates.
    """

    contract = ""

    def __init__(self, model: ModelProvider | None = None) -> None:
        self.model = model

    def _generate(self, prompt: str, context: dict) -> dict:
        if self.model is None:
            raise ProviderUnavailableError(
                f"skill {self.contract}: 未配置 AI 服务（VENCERTIA_MODEL_PROVIDER）"
            )
        return self.model.generate_structured(prompt, {"kind": self.contract}, context)


class MarketOpportunitySkill(_NarrativeSkillBase):
    contract = "MarketOpportunityContract"

    def run(self, context: dict) -> SkillCandidate:
        payload = self._generate(MARKET_PROMPT, context)
        return SkillCandidate(
            skill="market_opportunity", version="v11.0", contract=self.contract,
            payload=payload, deterministic=False,
        )


class FinancialModelSkill(_NarrativeSkillBase):
    contract = "FinancialModelContract"

    def run(self, context: dict) -> SkillCandidate:
        payload = self._generate(FINANCIAL_PROMPT, context)
        return SkillCandidate(
            skill="financial_model", version="v11.0", contract=self.contract,
            payload=payload, deterministic=False,
        )


class PlanNarrativeSkill(_NarrativeSkillBase):
    contract = "PlanNarrativeContract"

    def run(self, context: dict) -> SkillCandidate:
        payload = self._generate(PLAN_PROMPT, context)
        return SkillCandidate(
            skill="plan_narrative", version="v11.0", contract=self.contract,
            payload=payload, deterministic=False,
        )


class FounderDiagnosisSkill(_NarrativeSkillBase):
    contract = "FounderDiagnosisContract"

    def run(self, context: dict) -> SkillCandidate:
        payload = self._generate(FOUNDER_PROMPT, context)
        return SkillCandidate(
            skill="founder_diagnosis", version="v11.0", contract=self.contract,
            payload=payload, deterministic=False,
        )


class ExecutionStrategySkill(_NarrativeSkillBase):
    contract = "ExecutionStrategyContract"

    def run(self, context: dict) -> SkillCandidate:
        payload = self._generate(EXECUTION_PROMPT, context)
        return SkillCandidate(
            skill="execution_strategy", version="v11.0", contract=self.contract,
            payload=payload, deterministic=False,
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
