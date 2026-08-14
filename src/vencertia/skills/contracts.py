"""Skill output contracts (v2.0) — pydantic, extra-forbid.

每份契约对应 legacy V11 一个专家角色的结构化输出。叙事内容允许自由文本，
但**数字与断言必须携带 source_claim_id 引用**，由 SkillRouter 的引用校验门
强制"有出处"（candidate → validation）。
"""

from __future__ import annotations

from pydantic import Field

from vencertia.domain import VencertiaBaseModel


class MarketItem(VencertiaBaseModel):
    claim_id: str
    statement: str
    evidence_summary: str = ""
    numbers: list[MarketNumber] = Field(default_factory=list)


class MarketNumber(VencertiaBaseModel):
    label: str
    value: str  # narrative value; MUST be sourced via source_claim_id
    source_claim_id: str


class MarketOpportunityContract(VencertiaBaseModel):
    thesis: str = ""
    items: list[MarketItem] = Field(default_factory=list)


class FinancialAssumption(VencertiaBaseModel):
    label: str
    value: str
    source_claim_id: str
    note: str = ""


class FinancialModelContract(VencertiaBaseModel):
    unit_economics: str = ""
    assumptions: list[FinancialAssumption] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)


class PlanItem(VencertiaBaseModel):
    title: str
    body: str
    source_claim_id: str = ""


class PlanNarrativeContract(VencertiaBaseModel):
    sections: list[PlanItem] = Field(default_factory=list)


class FounderSignal(VencertiaBaseModel):
    label: str
    observation: str
    source_claim_id: str = ""


class FounderDiagnosisContract(VencertiaBaseModel):
    thesis: str = ""
    signals: list[FounderSignal] = Field(default_factory=list)


class ExecutionStep(VencertiaBaseModel):
    step: str
    rationale: str
    source_claim_id: str = ""


class ExecutionStrategyContract(VencertiaBaseModel):
    steps: list[ExecutionStep] = Field(default_factory=list)


class BusinessPlanNarrativeContract(VencertiaBaseModel):
    sections: list[PlanItem] = Field(default_factory=list)


CONTRACTS: dict[str, type[VencertiaBaseModel]] = {
    "MarketOpportunityContract": MarketOpportunityContract,
    "FinancialModelContract": FinancialModelContract,
    "PlanNarrativeContract": PlanNarrativeContract,
    "FounderDiagnosisContract": FounderDiagnosisContract,
    "ExecutionStrategyContract": ExecutionStrategyContract,
    "BusinessPlanNarrativeContract": BusinessPlanNarrativeContract,
}
