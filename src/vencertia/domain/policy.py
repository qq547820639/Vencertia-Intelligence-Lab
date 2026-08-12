"""Policy/Invariant/Heuristic — three-layer separated rules, versioned."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from vencertia.domain.base import RuleKind, VencertiaBaseModel


class Rule(VencertiaBaseModel):
    id: str
    kind: RuleKind
    name: str
    description: str = ""
    params: dict = Field(default_factory=dict)
    version: str = "1.0"
    enabled: bool = True
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class RuleSet(VencertiaBaseModel):
    rules: list[Rule] = Field(default_factory=list)
    version: str = "1.0"

    def by_kind(self, kind: RuleKind) -> list[Rule]:
        return [r for r in self.rules if r.kind == kind.value or r.kind == kind]

    def get(self, name: str) -> Rule | None:
        for rule in self.rules:
            if rule.name == name:
                return rule
        return None
