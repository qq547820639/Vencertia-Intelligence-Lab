"""FinancialCapability — candidate FinancialSnapshot / unit economics (mock)."""

from __future__ import annotations

from uuid import uuid4

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import Claim, ClaimType, Scope
from vencertia.runtime.context import ContextBundle


class FinancialCapability:
    name = "financial"

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        claims = [
            Claim(
                id=f"CLM_{uuid4().hex}",
                statement="Unit economics are viable at target price point.",
                scope=Scope.PROJECT,
                claim_type=ClaimType.HYPOTHESIS.value,
                project_id=context.project.id if context.project else None,
            )
        ]
        return CapabilityResult(
            claims=claims,
            notes=[
                "Candidate financial snapshot; SYSTEM_DERIVED metrics require human confirmation."
            ],
        )
