"""ChallengerCapability — counter-evidence / devil's advocate candidates.

v1.2 (V-3): alongside the legacy counter-evidence (which feeds the
``conflict_engine``), the capability now emits a structured
:class:`ModelCritique` so downstream consumers can machine-read the critique
findings instead of parsing prose.
"""

from __future__ import annotations

from uuid import uuid4

from vencertia.capabilities.base import CapabilityResult
from vencertia.domain import (
    CritiqueFindingType,
    Direction,
    Evidence,
    EvidenceType,
    ModelCritique,
    ModelRisk,
    Scope,
)
from vencertia.domain.context import ContextBundle


class ChallengerCapability:
    name = "challenger"

    def run(self, task: str, context: ContextBundle) -> CapabilityResult:
        claim_ids = [b.claim_id for b in context.critical_assumptions]
        decision_id = context.latest_decisions[0].id if context.latest_decisions else "UNKNOWN"
        evidence = [
            Evidence(
                id=f"E_{uuid4().hex}",
                claim_ids=claim_ids,
                scope=Scope.PROJECT,
                evidence_type=EvidenceType.LLM_INFERENCE.value,
                source="Challenger capability (mock): interviews may overstate willingness to pay.",
                directness=0.4,
                reliability=0.5,
                relevance=0.8,
                strength=0.4,
                supports_or_contradicts=Direction.CONTRADICTS.value,
                authority_level="LLM_INFERENCE",
                verification="UNKNOWN",
            )
        ]
        critique = ModelCritique(
            id="MCR_" + uuid4().hex,
            decision_id=decision_id,
            missing_variables=["willingness-to-pay (interviews may overstate it)"],
            hidden_dependencies=[],
            regime_risks=[],
            double_counting=["willingness-to-pay and adoption risk may overlap"],
            model_risk=ModelRisk.MEDIUM,
            findings=[
                CritiqueFindingType.MISSING_VARIABLE,
                CritiqueFindingType.DOUBLE_COUNTING,
            ],
            recommendation="Validate willingness-to-pay with real payment evidence.",
        )
        return CapabilityResult(
            evidence=evidence,
            critique=critique,
            notes=["Adversarial candidate; triggers conflict detection."],
        )
