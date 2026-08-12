"""CompanyIntelligenceCapability — CompanyCase/ClaimTrace retrieval & compare.

Honors Company Case isolation (ADR-004): output evidence has scope=COMPANY_CASE
and never updates project beliefs directly.
"""

from __future__ import annotations

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import Evidence, Scope, utcnow
from vencertia.domain.context import ContextBundle
from vencertia.repositories.base import Repository


class CompanyIntelligenceCapability:
    name = "company_intelligence"

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        cases = self.repo.list_company_cases()
        evidence: list[Evidence] = []
        for case in cases:
            evidence.append(
                Evidence(
                    id=f"E_CMP_{case.company_id}",
                    claim_ids=[],
                    scope=Scope.COMPANY_CASE,
                    evidence_type="COMPANY_CASE_FACT",
                    source=(
                        f"Company case {case.canonical_name} "
                        f"(roles={case.case_roles}, confidence={case.overall_confidence})."
                    ),
                    directness=0.5,
                    reliability=0.6,
                    relevance=0.5,
                    strength=0.5,
                    supports_or_contradicts="NEUTRAL",
                    authority_level="MODEL_PRIOR",
                    verification="ESTIMATED",
                    transferability=None,
                    observed_at=utcnow(),
                )
            )
        return CapabilityResult(
            evidence=evidence,
            notes=[
                "Company-case candidates are isolated; transferability review is required "
                "before any project-belief effect."
            ],
        )
