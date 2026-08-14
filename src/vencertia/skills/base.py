"""Skill layer (v2.0) — 经验资产作为一等公民.

A Skill packages ONE methodology artifact (migrated from the legacy V11
specialist prompt packs in ``legacy/agent_v11/``) as: versioned prompt
template + structured output contract + candidate-only authority.

权力边界（与三层架构一致）：
- 规则（确定性引擎）拥有状态 —— 脊椎；
- Skill 承载经验（提示词资产 + 输出契约）—— 肌肉；
- Skill 永远只产出候选（SkillCandidate），确定性校验门（引用真实 claim、
  契约校验）通过后才可被下游展示层使用。Skill 无写权。

Mock 模式：每个 skill 提供确定性模板回退（deterministic=True），产出引用
真实上下文的诚实内容，全链路离线可验证；真实 LLM 凭据配置后即插即用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import ValidationError

from vencertia.domain import VencertiaBaseModel


class SkillMetadata(VencertiaBaseModel):
    """Registry entry for one experience asset."""

    name: str
    version: str  # asset provenance, e.g. "v11.0"
    v11_source: str  # legacy source prompt file (experience lineage)
    description: str
    contract: str  # pydantic output contract name
    stage: str  # idea | decision | bp | execution


class SkillCandidate(VencertiaBaseModel):
    """A skill's structured output — CANDIDATE only, never truth."""

    skill: str
    version: str
    contract: str
    payload: dict
    deterministic: bool  # True = mock template fallback (offline)


class SkillTrace(VencertiaBaseModel):
    """One orchestration step (auditable)."""

    skill: str
    version: str
    status: str  # OK | REJECTED (validation) | SKIPPED (not applicable)
    note: str = ""


class Skill(Protocol):
    """A skill must expose metadata + produce a validated candidate."""

    def run(self, context: dict) -> SkillCandidate: ...


class SkillValidationError(ValueError):
    """A skill candidate failed the deterministic validation gate."""


@dataclass
class SkillRegistry:
    """Versioned catalog of experience assets (rules: registry, not magic)."""

    _skills: dict[str, tuple] = field(default_factory=dict)  # name -> (skill, metadata)

    def register(self, skill: Skill, metadata: SkillMetadata) -> None:
        self._skills[metadata.name] = (skill, metadata)

    def get(self, name: str) -> tuple | None:
        return self._skills.get(name)

    def list(self) -> list[SkillMetadata]:
        return [metadata for _, metadata in sorted(self._skills.values(), key=lambda t: t[1].name)]


class SkillRouter:
    """编排层：按阶段路由到 skill，产出候选并执行确定性校验门。

    校验门（candidate → validation）：
      1. 契约校验 —— 输出必须通过其 pydantic 契约（extra forbid）；
      2. 引用校验 —— narrative 中的数字/断言引用必须指向上下文中真实存在的
         claim/belief（禁止无出处数字）。
    任何一门失败 ⇒ 该 skill 标记 REJECTED，绝不静默降级成伪造内容。
    """

    def __init__(self, registry: SkillRegistry, validation=None) -> None:
        self.registry = registry
        self.validation = validation or validate_references

    def skills_for_stage(self, stage: str) -> list[SkillMetadata]:
        return [m for m in self.registry.list() if m.stage == stage]

    def run_stage(self, stage: str, context: dict) -> tuple[list[SkillCandidate], list[SkillTrace]]:
        candidates: list[SkillCandidate] = []
        traces: list[SkillTrace] = []
        for metadata in self.skills_for_stage(stage):
            skill, _ = self.registry.get(metadata.name)
            try:
                candidate = skill.run(context)
                # gate 1: contract validation (pydantic)
                contract_model = candidate_contract(metadata.contract)
                contract_model.model_validate(candidate.payload)
                # gate 2: reference validation (numbers must have sources)
                self.validation(candidate, context)
                candidates.append(candidate)
                traces.append(SkillTrace(skill=metadata.name, version=metadata.version, status="OK"))
            except (ValidationError, SkillValidationError, ValueError) as exc:
                traces.append(
                    SkillTrace(
                        skill=metadata.name,
                        version=metadata.version,
                        status="REJECTED",
                        note=str(exc)[:200],
                    )
                )
        return candidates, traces


def candidate_contract(name: str):
    from vencertia.skills.contracts import CONTRACTS

    return CONTRACTS[name]


def validate_references(candidate: SkillCandidate, context: dict) -> None:
    """Every referenced claim id must exist in the context (no fabricated sources)."""
    valid_ids = set(context.get("claim_ids") or [])
    payload = candidate.payload

    def check(item: dict) -> None:
        for key in ("source_claim_id", "source_claim_ids", "claim_id"):
            value = item.get(key)
            refs = value if isinstance(value, list) else ([value] if value else [])
            for ref in refs:
                if ref not in valid_ids:
                    raise SkillValidationError(
                        f"skill {candidate.skill} 引用了不存在的 claim {ref!r}"
                    )

    def walk(items: list) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            check(item)
            for number in item.get("numbers", []) or []:
                if isinstance(number, dict):
                    check(number)

    for section in payload.get("sections", []):
        if isinstance(section, dict):
            walk(section.get("items", []) or [])
    walk(payload.get("items", []) or [])
    for item in payload.get("assumptions", []):
        if isinstance(item, dict):
            check(item)
    for item in payload.get("signals", []):
        if isinstance(item, dict):
            check(item)
    for item in payload.get("steps", []):
        if isinstance(item, dict):
            check(item)
